import json
import pandas as pd
import sendgrid
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from method.seir import get_default, gen_initial, project_resource, transform_seir, SEIR

# Data preparation
assumption = {
    'avg_weight': 60  # น้ำหนักเฉลี่ยประชากรในพื้นที่
}

resource_consumption = {
    # facility
    'p_aiir': 0.05,  # % % การใช้ห้อง negative pressure ที่ใช้จากจำนวนผู้ป่วยติดเชื้อ

    # machine
    'p_vent': 1,  # % การใช้ ventilators จากจำนวนผู้ป่วย ICU
    'p_ecmo': 0.5,  # % การใช้ ECMO จากจำนวนผู้ป่วย ICU
    'rate_ct_scan': 2,  # CT-Scan ตรวจได้ชั่วโมงกี่คน
    'rate_cxr': 6,  # Chest X-Ray ตรวจได้ชั่วโมงละกี่คน
    'd_pcr': 6,  # Lab PCR ใช้ระยะเวลาตรวจ case ละกี่ชั่วโมง

    # material
    'favipiravir_tab': 200,  # mg
    'lopinavir_tab': 200,  # mg
    'darunavir_tab': 600,  # mg
    'ritonavir_tab': 50,  # mg
    'chloroquine_tab': 250,  # mg
    'ppe_used_per_shift_per_staff': 1,  # เจ้าหน้าที่เปลี่ยน PPE Set กะละกี่ครั้ง
    'ppe_used_per_swab': 1,  # จำนวน PPE Set ที่ใช้ในการ Swab

    # จำนวน PPE Set ที่ใช้ในการติดตั้งเครื่องช่วยหายใจ
    'ppe_used_per_install_venti': 1,
    'ppe_used_per_suction': 1,  # จำนวน PPE Set ที่ใช้ในการทำ Suction
    'icu_suction_times': 9,  # จำนวนครั้งการทำ suction ของผู้ป่วยที่ใช้เครื่องช่วยหายใจ

    # man
    'staff_shift_workshour': 8,  # จำนวนชั่วโมงทำงานของเจ้าหน้าที่ใน 1 กะ
    'staff_nurse_icu_per_pt': (24 * 1) / 2,

    # (จำนวนชั่วโมงทำงาน*จำนวนบุคลากรในทีม)/จำนวนผู้ป่วยที่ดูแล
    'staff_nurse_aid_icu_per_pt': (24 * 1) / 2,
}


def supply_estimation(event, context):
    user_input = json.loads(event['body'])
    user_input['start_date'] = pd.to_datetime(user_input['start_date'])
    user_input['social_distancing'] = [
        user_input['social_distancing'],
        user_input['social_distancing_start'],
        user_input['social_distancing_end']
    ]
    params = get_default()

    initial_data, params = gen_initial(params, user_input)

    SEIR_df = SEIR(params, initial_data, user_input['steps'])
    hos_load_df = transform_seir(
        SEIR_df, params, user_input['hospital_market_share'])
    resource_projection_df = project_resource(
        hos_load_df, resource_consumption)

    # transform dataframes to json serializable objects
    seir_json = SEIR_df.set_index('date').to_json(
        orient='split', date_format='iso')
    resource_json = resource_projection_df.set_index(
        'date').to_json(orient='split', date_format='iso')

    body = ''.join([
        '{"seir":',
        seir_json,
        ',"resource_json":',
        resource_json,
        '}'
    ])

    response = {
        "statusCode": 200,
        "body": body
    }

    return response


def supply_service(event, context):
    SENDGRID_API_KEY = "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"

    # Get post detail
    user_input = json.loads(event['body'])
    user_input['start_date'] = pd.to_datetime(user_input['start_date'])
    user_input['social_distancing'] = [
        user_input['social_distancing'],
        user_input['social_distancing_start'],
        user_input['social_distancing_end']
    ]
    from_email = user_input['from_email']
    to_email = user_input['to_email']
    params = get_default()

    # Prediction
    initial_data, params = gen_initial(params, user_input)

    SEIR_df = SEIR(params, initial_data, user_input['steps'])
    hos_load_df = transform_seir(
        SEIR_df, params, user_input['hospital_market_share'])
    resource_projection_df = project_resource(
        hos_load_df, resource_consumption)

    seir_json = SEIR_df.set_index('date').to_json(
        orient='split', date_format='iso')
    resource_json = resource_projection_df.set_index(
        'date').to_json(orient='split', date_format='iso')

    # Prepare EMAIL
    message = Mail(
        from_email=from_email,
        to_emails=to_email)
    message.template_id = 'd-12f42d19558d4dac800536a34eb6ffee'
    message.dynamic_template_data = {
        'subject': "CoCare report for your hospital"
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
