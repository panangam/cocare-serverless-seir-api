from datetime import datetime
import pandas as pd
import numpy as np


def get_default_params():
    params = {'d_incubation': 6.1,
              'd_infectious': 2.3,
              'd_test': 2,
              'd_death': 28,
              'los_hos_mild': 14,
              'los_hos_severe': 28,
              'los_hos_critical': 28,
              'los_home_mild': 7,
              'los_home_severe': 7,
              'los_hotel_mild': 7,
              'los_hotel_severe': 7,
              'cfr': 0.023,
              'p_critical': 0.05 - 0.023,
              'p_severe': 0.14,
              'p_mild': 0.81,
              'p_mild_hotel': 0,
              'p_mild_home': 0,
              'p_severe_hotel': 0,
              'p_severe_home': 0,
              'p_test_positive': 0.1,
              # Date today
              'today': datetime.today().strftime('%Y-%m-%d'),
              # Social distancing
              'social_distancing_rate': 0,
              'social_distance_day_start': 0,
              'social_distance_day_end': 1,
              'hospital_market_share': 1,
              # Cases default_data
              'doubling_time': 7,
              'total_confirm_cases': 1,
              'active_cases': 1,
              'critical_cases': -1,
              'regional_population': 66000000,
              'death': 0,
              # Predict for
              'steps': 14
              }
    return params


def gen_initial(params, user_input):
    doubling_time = int(user_input.get(
        'doubling_time', params['doubling_time']))
    total_confirm_cases = int(user_input.get(
        'total_confirm_cases', params['total_confirm_cases']))
    regional_population = int(user_input.get(
        'regional_population', params['regional_population']))
    active_cases = int(user_input['active_cases'])
    critical_cases = user_input.get('critical_cases')
    if critical_cases < 0:
        critical_cases = (params['p_critical'] + params['cfr']) * active_cases
    death = int(user_input.get(
        'death', params['death']))

    growth = 2 ** (1 / doubling_time) - 1
    gamma = 1 / params['d_infectious']
    sigma = 1 / params['d_incubation']
    pui = growth * total_confirm_cases * params['d_test']
    i = pui * (growth + (1 / params['d_test'])) / gamma
    e = i * (growth + gamma) / sigma
    beta = (growth + gamma) * (growth + sigma) / sigma
    r0 = beta / gamma
    s = regional_population - total_confirm_cases - pui - i - e

    # update params
    params['r0'] = r0
    params['n'] = regional_population
    params['social_distancing_rate'] = user_input['social_distancing']

    # create initial data for start date
    recover = total_confirm_cases - active_cases - death
    initial_data = {
        'date': user_input['start_date'],
        's': s,
        'e': e,
        'i': i,
        'pui': pui,
        'hos_mild': (active_cases - critical_cases) * params['p_mild'] / (params['p_mild'] + params['p_severe']),
        'hos_severe': (active_cases - critical_cases) * params['p_severe'] / (params['p_mild'] + params['p_severe']),
        'hos_critical': critical_cases * params['p_critical'] / (params['p_critical'] + params['cfr']),
        'hos_fatal': critical_cases * params['cfr'] / (params['p_critical'] + params['cfr']),
        'home_mild': 0,
        'home_severe': 0,
        'hotel_mild': 0,
        'hotel_severe': 0,
        'r_mild_hos': params['p_mild'] * recover,
        'r_mild_home': 0,
        'r_mild_hotel': 0,
        'r_severe_hos': params['p_severe'] * recover,
        'r_severe_home': 0,
        'r_severe_hotel': 0,
        'r_critical_hos': (params['p_critical'] + params['cfr']) * recover,
        'death': death,
        'new_hos_mild': 0,
        'new_hos_severe': 0,
        'new_hos_critical': 0,
        'new_pui': 0
    }

    return initial_data, params


def SEIR(params, initial_data, steps=1):
    # do thing
    time_series = pd.DataFrame([initial_data.values()], columns=list(initial_data.keys()))
    for i in range(steps):
        sod = time_series.iloc[-1]
        diff = get_differentials(params, sod, i)
        eod = sod.copy()
        eod[1:] += diff
        eod[0] = sod[0] + pd.Timedelta('1 day')
        # reset new case
        eod[-1] = diff[-1]
        eod[-2] = diff[-2]
        eod[-3] = diff[-3]
        eod[-4] = diff[-4]
        time_series = time_series.append(eod, ignore_index=True)
    return time_series


def get_differentials(params, sod, day=0):
    # params
    if day < params['social_distancing_rate'][1]:
        r0 = params['r0']
    elif day <= params['social_distancing_rate'][2]:
        r0 = (1 - params['social_distancing_rate'][0]) * params['r0']
    else:
        r0 = params['r0']
    d_test = params['d_test']
    d_death = params['d_death']
    los_hos_mild = params['los_hos_mild']
    los_hos_severe = params['los_hos_severe']
    los_hos_critical = params['los_hos_critical']
    los_home_mild = params['los_home_mild']
    los_home_severe = params['los_home_mild']
    los_hotel_mild = params['los_hotel_mild']
    los_hotel_severe = params['los_hotel_mild']
    n = params['n']

    # compute rate
    sigma = 1 / params['d_incubation']
    gamma = 1 / params['d_infectious']
    beta = r0 * gamma

    # percentage of severity
    p_fatal = params['cfr']
    p_critical = params['p_critical']
    p_severe = params['p_severe']
    p_mild = 1 - p_severe - p_critical - p_fatal

    # transfer pt to home or hotel (only mild & severe)
    p_mild_hotel = params['p_mild_hotel']
    p_mild_home = params['p_mild_home']
    p_mild_hos = 1 - p_mild_home - p_mild_hotel
    p_severe_hotel = params['p_severe_home']
    p_severe_home = params['p_severe_home']
    p_severe_hos = 1 - p_severe_home - p_severe_hotel

    # start of day
    s = sod.s
    e = sod.e
    i = sod.i
    pui = sod.pui
    hos_mild = sod.hos_mild
    hos_severe = sod.hos_severe
    hos_critical = sod.hos_critical
    hos_fatal = sod.hos_fatal
    home_mild = sod.home_mild
    home_severe = sod.home_severe
    hotel_mild = sod.hotel_mild
    hotel_severe = sod.hotel_severe

    # compute diff in this period
    diff_s = -beta * i * s / n
    diff_e = beta * i * s / n - sigma * e
    diff_i = sigma * e - gamma * i
    diff_pui = gamma * i - (1 / d_test) * pui
    diff_hos_mild = (
            p_mild * (1 / d_test) * pui
            - p_mild_home * (1 / (los_hos_mild - los_home_mild)) * hos_mild
            - p_mild_hotel * (1 / (los_hos_mild - los_hotel_mild)) * hos_mild
            - (1 / los_hos_mild) * hos_mild
    )
    diff_hos_severe = (
            p_severe * (1 / d_test) * pui
            - p_severe_home * (1 / (los_hos_severe - los_home_severe)) * hos_severe
            - p_severe_hotel * (1 / (los_hos_severe - los_hotel_severe)) * hos_severe
            - (1 / los_hos_severe) * hos_severe
    )
    diff_hos_critical = p_critical * (1 / d_test) * pui - (1 / los_hos_critical) * hos_critical
    diff_hos_fatal = p_fatal * (1 / d_test) * pui - (1 / d_death) * hos_fatal
    diff_home_mild = (
            p_mild_home * (1 / (los_hos_mild - los_home_mild)) * hos_mild
            - (1 / (los_hos_mild - los_home_mild)) * home_mild
    )
    diff_home_severe = (
            p_severe_home * (1 / (los_hos_severe - los_home_severe)) * hos_severe
            - (1 / (los_hos_severe - los_home_severe)) * home_severe
    )
    diff_hotel_mild = (
            p_mild_hotel * (1 / (los_hos_mild - los_hotel_mild)) * hos_mild
            - (1 / (los_hos_mild - los_hotel_mild)) * hotel_mild
    )
    diff_hotel_severe = (
            p_severe_hotel * (1 / (los_hos_severe - los_hotel_severe)) * hos_severe
            - (1 / (los_hos_severe - los_hotel_severe)) * hotel_severe
    )
    diff_r_mild_hos = (1 / los_hos_mild) * hos_mild
    diff_r_mild_home = (1 / (los_hos_mild - los_home_mild)) * home_mild
    diff_r_mild_hotel = (1 / (los_hos_mild - los_hotel_mild)) * hotel_mild
    diff_r_severe_hos = (1 / los_hos_severe) * hos_severe
    diff_r_severe_home = (1 / (los_hos_severe - los_home_severe)) * home_severe
    diff_r_severe_hotel = (1 / (los_hos_severe - los_hotel_severe)) * hotel_severe
    diff_r_critical = (1 / los_hos_critical) * hos_critical
    diff_death = (1 / d_death) * hos_fatal

    # compute new confirm case for resource projection
    new_hos_mild = p_mild * (1 / d_test) * pui
    new_hos_severe = p_severe * (1 / d_test) * pui
    new_hos_critical = (p_critical + p_fatal) * (1 / d_test) * pui
    new_pui = gamma * i

    return [diff_s, diff_e, diff_i, diff_pui, diff_hos_mild, diff_hos_severe, diff_hos_critical,
            diff_hos_fatal, diff_home_mild, diff_home_severe, diff_hotel_mild, diff_hotel_severe,
            diff_r_mild_hos, diff_r_mild_home, diff_r_mild_hotel, diff_r_severe_hos,
            diff_r_severe_home, diff_r_severe_hotel, diff_r_critical, diff_death,
            new_hos_mild, new_hos_severe, new_hos_critical, new_pui]


def summarize_seir(seir_df):
    summary_df = pd.DataFrame()
    summary_df['date'] = seir_df['date']
    summary_df['recovered'] = (
            seir_df['r_mild_hos']
            + seir_df['r_mild_home']
            + seir_df['r_mild_hotel']
            + seir_df['r_severe_hos']
            + seir_df['r_severe_home']
            + seir_df['r_severe_hotel']
            + seir_df['r_critical_hos']
    )
    summary_df['death'] = seir_df['death']
    summary_df['active_cases'] = (
            seir_df['hos_mild']
            + seir_df['hos_severe']
            + seir_df['hos_critical']
            + seir_df['hos_fatal']
            + seir_df['home_mild']
            + seir_df['home_severe']
            + seir_df['hotel_mild']
            + seir_df['hotel_severe']
    )
    summary_df['total_confirm_cases'] = summary_df['active_cases'] + summary_df['recovered'] + summary_df['death']
    summary_df['new_cases'] = seir_df['new_hos_mild'] + seir_df['new_hos_severe'] + seir_df['new_hos_critical']
    summary_df['new_active_cases'] = summary_df['active_cases'].diff()
    summary_df['new_recovered'] = summary_df['recovered'].diff()
    summary_df['new_death'] = summary_df['death'].diff()
    summary_df['pui'] = seir_df['pui']
    summary_df['s'] = seir_df['s']
    summary_df['e'] = seir_df['e']
    summary_df['i'] = seir_df['i']

    return summary_df


def recent_cases_to_doubling_time(recent_cases, period=0):
    if period == 0 or period > len(recent_cases): period = len(recent_cases)
    return period * (np.log(2) / np.log(recent_cases[0] / recent_cases[period - 1]))
