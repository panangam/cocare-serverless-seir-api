import json
import pandas as pd
import sendgrid
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from method.seir import gen_initial, prepare_input, seir_estimation


def supply_estimation(event, context):
    # Load user input
    user_input = json.loads(event['body'])

    # Model and prediction
    user_input, default_params = prepare_input(user_input)
    initial_data, params = gen_initial(default_params, user_input)
    seir_json, resource_json = seir_estimation(
        params, initial_data, user_input)

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
    SENDGRID_API_KEY = "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"

    # Get post detail
    user_input = json.loads(event['body'])
    user_input, default_params = prepare_input(user_input)
    from_email = user_input['from_email']
    to_email = user_input['to_email']

    # Model and prediction
    initial_data, params = gen_initial(default_params, user_input)
    seir_json, resource_json = seir_estimation(
        params, initial_data, user_input)

    # Population calculator
    population = [120, 125, 130, 145, 160, 190,
                  210, 220, 420, 670, 1040, 1240, 1450, 1600]
    pop_y = ''
    pop_x = ''
    label_x = ''
    for index, i in enumerate(population):
        pop_y += str(i)
        pop_x += str(index)
        label_x += "D{}".format(str(index+1))
        if index < (len(population) - 1):
            pop_y += '%2C'
            pop_x += '%2C'
            label_x += '%7C'

    # Supply ICU calculator
    icu_supply = [1000, 890, 750, 640, 550,
                  320, 180, 110, 80, 60, 30, 20, 12, 5, 0]
    icu_demand = [0, 4, 12, 20, 25, 38,
                  44, 48, 52, 56, 60, 80, 90, 110, 160]
    icu_supply_y = ''
    icu_supply_x = ''
    icu_supply_label_x = ''
    icu_demand_y = ''
    icu_demand_x = ''
    icu_demand_label_x = ''
    for index, i in enumerate(icu_supply):
        icu_supply_y += str(i)
        icu_supply_x += str(index)
        # icu_supply_x += "D{}".format(str(index+1))
        if index < (len(icu_supply) - 1):
            icu_supply_y += '%2C'
            icu_supply_x += '%2C'
            # icu_supply_x += '%7C'
    for index, i in enumerate(icu_demand):
        icu_demand_y += str(i)
        icu_demand_x += str(index)
        # icu_demand_x += "D{}".format(str(index+1))
        if index < (len(icu_demand) - 1):
            icu_demand_y += '%2C'
            icu_demand_x += '%2C'
            # icu_demand_x += '%7C'

    # Prepare EMAIL
    message = Mail(
        from_email=from_email,
        to_emails=to_email)
    message.template_id = 'd-12f42d19558d4dac800536a34eb6ffee'
    message.dynamic_template_data = {
        'subject': "CoCare report for โรงพยาบาล {}".format(user_input["hospital_name"]),
        # "writing_date": user_input["start_date"],
        "population": user_input["regional_population"],
        "hos_name": user_input["hospital_name"],
        "hos_market_share": user_input["hospital_market_share"],
        "region": user_input["hospital_region"],
        "doubling_time": user_input["doubling_time"],
        "total_cases": user_input["total_confirm_cases"],
        "active_cases": user_input["active_cases"],
        "critical_cases": user_input["critical_cases"],
        "death_cases": user_input["death"],
        "pop_x": pop_x,
        "pop_y": pop_y,
        "label_x": label_x,
        "icu_supply_y": icu_supply_y,
        "icu_supply_x": icu_supply_x,
        # "icu_supply_label_x": icu_supply_label_x,
        "icu_demand_y": icu_demand_y,
        "icu_demand_x": icu_demand_x,
        # "icu_demand_label_x": icu_demand_label_x,
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
