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
