import json
import os
import base64
import math

import pandas as pd
import sendgrid
import matplotlib.pyplot as plt
from io import BytesIO
from dotenv import load_dotenv
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from model.seir import gen_initial, summarize_seir, get_default_params
from model.resource_projection import get_resource_consumption
from model_run import seir_estimation
from datetime import timedelta, date, datetime

load_dotenv()


def seir_df_to_json(seir_df, resource_df):
    seir_json = seir_df.set_index('date').to_json(
        orient='split', date_format='iso')
    resource_json = resource_df.set_index(
        'date').to_json(orient='split', date_format='iso')
    return seir_json, resource_json


def prepare_input(user_input):
    default_params = get_default_params()
    user_input['start_date'] = pd.to_datetime(
        user_input.get('start_date', default_params['today']))
    user_input['social_distancing'] = [
        float(user_input.get('social_distancing',
                             default_params['social_distancing_rate'])),
        float(user_input.get('social_distancing_start',
                             default_params['social_distance_day_start'])),
        float(user_input.get('social_distancing_end',
                             default_params['social_distance_day_end']))
    ]
    hospital_region = user_input.get('hospital_region')
    user_input['area'] = hospital_region.split('(')[0].rstrip()
    user_input['regional_population'] = float(
        hospital_region.split('(')[1].split()[0].split('คน')[0].replace(',', ''))
    user_input['hospital_market_share'] = user_input.get(
        'hospital_market_share', default_params['hospital_market_share'])
    user_input['doubling_time'] = user_input.get(
        'doubling_time', default_params['doubling_time'])
    user_input['doubling_time'] = user_input.get(
        'doubling_time', default_params['doubling_time'])
    user_input['critical_cases'] = user_input.get(
        'critical_cases', default_params['critical_cases'])
    user_input['death'] = user_input.get(
        'death', default_params['death'])
    user_input['icu_supply'] = user_input.get('icu_supply', 0)
    return user_input, default_params


def supply_estimation(event, context):
    # Load user input
    user_input = json.loads(event['body'])

    # Model and prediction
    model_input, default_params = prepare_input(user_input)
    initial_data, params = gen_initial(default_params, model_input)
    resource_consumption = get_resource_consumption()
    seir_df, hos_load_df, resource_df = seir_estimation(
        params, initial_data, user_input, resource_consumption)
    seir_json, resource_json = seir_df_to_json(seir_df, resource_df)

    # update user_input
    user_input['critical_cases'] = round(initial_data['hos_critical'] + initial_data['hos_fatal'], 0)

    response_body = ''.join([
        '{"seir":',
        seir_json,
        ',"resource_json":',
        resource_json,
        '}'
    ])

    response = {
        "statusCode": 200,
        "body": response_body
    }

    return response


def supply_service(event, context):
    SENDGRID_API_KEY = os.getenv("SENDGRID_KEY")

    # Get post detail
    user_input = json.loads(event['body'])
    user_input, default_params = prepare_input(user_input)
    from_email = user_input['from_email']
    to_email = user_input['to_email']

    # Model and prediction
    initial_data, params = gen_initial(default_params, user_input)
    resource_consumption = get_resource_consumption()
    seir_df, hos_load_df, resource_df = seir_estimation(
        params, initial_data, user_input, resource_consumption)
    seir_json, resource_json = seir_df_to_json(seir_df, resource_df)

    # update user_input
    user_input['critical_cases'] = round(initial_data['hos_critical'] + initial_data['hos_fatal'], 0)

    # Population calculator
    summary_df = summarize_seir(seir_df)
    patients = summary_df['active_cases'].to_list()

    future_hos_mild = math.floor(seir_df.tail(1)['hos_mild'])
    future_hos_severe = math.floor(seir_df.tail(1)['hos_severe'])
    future_hos_critical = math.floor(seir_df.tail(1)['hos_critical'])
    future_total = future_hos_mild + future_hos_severe + future_hos_critical

    # Population calculator
    pop_y = ''
    pop_x = ''
    label_x = ''
    pop_string = ''
    for index, i in enumerate(patients):
        pop_y += str(i)
        pop_x += str(index)
        pop_string += str(math.floor(i))
        label_x += str((date.today() +
                        timedelta(days=index + 1)).strftime('%-d/%-m'))
        if index < (len(patients) - 1):
            pop_y += ','
            pop_x += ','
            label_x += '|'
            pop_string += '|'

    # Supply ICU calculator
    icu_demand = resource_df['bed_icu'].to_list()
    icu_supply_y = ''
    icu_supply_x = ''
    icu_supply_label_x = ''
    icu_demand_y = ''
    icu_demand_x = ''
    icu_demand_label_x = ''
    icu_string = ''
    icu_supply_y = ''
    for index, i in enumerate(icu_demand):
        icu_demand_y += str(i)
        icu_demand_x += str(index)
        icu_string += str(math.floor(i))
        icu_supply_y += str(user_input['icu_supply'])
        icu_supply_label_x += str((date.today() +
                                   timedelta(days=index + 1)).strftime('%-d/%-m'))
        if index < (len(icu_demand) - 1):
            icu_demand_y += ','
            icu_demand_x += ','
            icu_supply_label_x += '|'
            icu_string += '|'
            icu_supply_y += ','

    # plotting
    fig, ax = plt.subplots(figsize=(16, 9))
    ax.plot(resource_df['date'], resource_df['bed_icu'])
    ax.legend(['ICU Bed'])
    img_stream = BytesIO()
    fig.savefig(img_stream, format='png')
    icu_image_base_64 = base64.b64encode(img_stream.getvalue()).decode()

    # Prepare EMAIL
    message = Mail(
        from_email=from_email,
        to_emails=to_email)
    message.template_id = 'd-3509900158194a85b1f3f6f73b5a953c'
    message.dynamic_template_data = {
        'subject': "CoCare report for โรงพยาบาล {}".format(user_input["hospital_name"]),
        'date': date.today().strftime('%-d/%-m/%Y'),
        "population": user_input["regional_population"],
        "hos_name": user_input["hospital_name"],
        "hos_market_share": user_input["hospital_market_share"],
        "region": user_input["area"],
        "doubling_time": user_input["doubling_time"],
        "total_cases": user_input["total_confirm_cases"],
        "active_cases": user_input["active_cases"],
        "critical_cases": user_input["critical_cases"],
        "future_total": str(future_total),
        "future_hos_mild": str(future_hos_mild),
        "future_hos_severe": str(future_hos_severe),
        "future_hos_critical": str(future_hos_critical),
        "death_cases": user_input["death"],
        "pop_x": pop_x,
        "pop_y": pop_y,
        "pop_string": pop_string,
        "label_x": label_x,
        "icu_x": icu_demand_x,
        "icu_y": icu_demand_y,
        "icu_supply_y": icu_supply_y,
        "label_icu_x": icu_supply_label_x,
        "icu_string": icu_string
    }

    try:
        sendgrid_client = SendGridAPIClient(api_key=SENDGRID_API_KEY)
        response = sendgrid_client.send(message)
        return {
            "statusCode": 200,
            "body": json.dumps({"message": "Complete email operation!"})
        }
    except Exception as e:
        print(e.message)
        return {
            "statusCode": 500,
            "body": json.dumps(e.message)
        }


def load_json(filename):
    with open('./data/' + filename) as json_file:
        return json.load(json_file)


if __name__ == '__main__':
    # test
    user_input = load_json('user_input.json')
    model_input, default_params = prepare_input(user_input)
    initial_data, params = gen_initial(default_params, model_input)
    resource_consumption = get_resource_consumption()
    seir_df, hos_load_df, resource_df = seir_estimation(
        params, initial_data, user_input, resource_consumption)
    summary_df = summarize_seir(seir_df)
