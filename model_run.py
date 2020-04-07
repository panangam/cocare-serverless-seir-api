from model.seir import gen_initial, summarize_seir, recent_cases_to_doubling_time, get_default_params, SEIR
from model.resource_projection import transform_seir, project_resource, get_resource_consumption
import pandas as pd
import numpy as np


def seir_estimation(params, initial_data, user_input, resource_consumption):
    predict_step = int(user_input.get('steps', params['steps']))
    hospital_market_share = float(user_input.get(
        'hospital_market_share', params['hospital_market_share']))
    seir_df = SEIR(params, initial_data, predict_step)
    hos_load_df = transform_seir(seir_df, params, hospital_market_share)
    resource_projection_df = project_resource(hos_load_df, resource_consumption)

    return seir_df, hos_load_df, resource_projection_df


model_input = {
    # ref situation
    'doubling_time': 7.5,
    'total_confirm_cases': 175,
    'active_cases': 90,
    'critical_cases': 23,  # TODO: optional parameter now not effect
    'death': 4,
    'recent_cases': [175, 163, 153, 141, 123, 114, 107, 106, 102, 91],
    # ref site
    'regional_population': 4997037,
    'hospital_market_share': 1,
    # predict period
    'start_date': pd.to_datetime('2020-04-05'),
    'steps': 100,
    # intervention
    'social_distancing': [0, 0, 1],
}

supply_level = {
    'bed_icu': 100,
    'bed': 1000,
    'ventilator': 50,
    'negative_pressure': 10,
    'ppe_mask': 100000,
    'drug_favipiravir': 235285,
}

if __name__ == '__main__':
    # compute doubling time
    doubling_time = recent_cases_to_doubling_time(model_input['recent_cases'], period=7)
    print('Doubling Time: ', doubling_time)
    model_input['doubling_time'] = doubling_time
    # Model and prediction
    params = get_default_params()
    initial_data, params = gen_initial(params, model_input)
    resource_consumption = get_resource_consumption()
    seir_df, hos_load_df, resource_df = seir_estimation(params, initial_data, model_input, resource_consumption)
    # Summarize SEIR
    summary_df = summarize_seir(seir_df)
    # Join with resource projection
    output_df = summary_df.merge(hos_load_df, left_on='date', right_on='date')
    output_df = output_df.merge(resource_df, left_on='date', right_on='date')
    output_df.to_csv('./result/covid19_thai_resource_simulation_ah12.csv',
                     encoding='utf-8')  # TODO: add area nam + doubling time + ref date
