import json
import pandas as pd

assumption = {
    'avg_weight': 60  # น้ำหนักเฉลี่ยประชากรในพื้นที่
}
resource_consumption = {
    ## facility
    'p_aiir': 0.05,  # % % การใช้ห้อง negative pressure ที่ใช้จากจำนวนผู้ป่วยติดเชื้อ
    ## machine
    'p_vent': 1,  # % การใช้ ventilators จากจำนวนผู้ป่วย ICU
    'p_ecmo': 0.5,  # % การใช้ ECMO จากจำนวนผู้ป่วย ICU
    'rate_ct_scan': 2,  # CT-Scan ตรวจได้ชั่วโมงกี่คน
    'rate_cxr': 6,  # Chest X-Ray ตรวจได้ชั่วโมงละกี่คน
    'd_pcr': 6,  # Lab PCR ใช้ระยะเวลาตรวจ case ละกี่ชั่วโมง
    ## material
    'favipiravir_tab': 200,  # mg
    'lopinavir_tab': 200,  # mg
    'darunavir_tab': 600,  # mg
    'ritonavir_tab': 50,  # mg
    'chloroquine_tab': 250,  # mg
    'ppe_used_per_shift_per_staff': 1,  # เจ้าหน้าที่เปลี่ยน PPE Set กะละกี่ครั้ง
    'ppe_used_per_swab': 1,  # จำนวน PPE Set ที่ใช้ในการ Swab
    'ppe_used_per_install_venti': 1,  # จำนวน PPE Set ที่ใช้ในการติดตั้งเครื่องช่วยหายใจ
    'ppe_used_per_suction': 1,  # จำนวน PPE Set ที่ใช้ในการทำ Suction
    'icu_suction_times': 9,  # จำนวนครั้งการทำ suction ของผู้ป่วยที่ใช้เครื่องช่วยหายใจ
    ## man
    'staff_shift_workshour': 8,  # จำนวนชั่วโมงทำงานของเจ้าหน้าที่ใน 1 กะ
    'staff_nurse_icu_per_pt': (24 * 1) / 2,
    # (จำนวนชั่วโมงทำงาน*จำนวนบุคลากรในทีม)/จำนวนผู้ป่วยที่ดูแล
    'staff_nurse_aid_icu_per_pt': (24 * 1) / 2,
    # (จำนวนชั่วโมงทำงาน*จำนวนบุคลากรในทีม)/จำนวนผู้ป่วยที่ดูแล
}


def hello(event, context):
    # sample_user_input = {
    #     'doubling_time': 6,
    #     'social_distancing': 0.5,
    #     'social_distancing_start': 50,
    #     'social_distancing_end': 80,
    #     'hospital_market_share': 0.5,
    #     'start_date': pd.to_datetime('2020-04-01'),
    #     'steps': 300,
    #     'regional_population': 66000000,
    #     'total_confirm_cases': 1400,
    #     'active_cases': 1000,
    #     'critical_cases': 20,
    #     'death': 10,
    # }

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
    hos_load_df = transform_seir(SEIR_df, params, user_input['hospital_market_share'])
    resource_projection_df = project_resource(hos_load_df, resource_consumption)

    # transform dataframes to json serializable objects
    seir_json = SEIR_df.set_index('date').to_json(orient='split', date_format='iso')
    resource_json = resource_projection_df.set_index('date').to_json(orient='split', date_format='iso')

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


def SEIR(params, initial_data, steps=1):
    # do thing
    time_series = pd.DataFrame([initial_data])
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
        time_series = time_series.append(eod, ignore_index=True)  # TODO: เพิ่ม new pt ด้วย
    return time_series


def get_differentials(params, sod, day=0):
    # params
    if day < params['social_distancing'][1]:
        r0 = params['r0']
    elif day <= params['social_distancing'][2]:
        r0 = (1 - params['social_distancing'][0]) * params['r0']
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

def get_default():
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
            'p_test_positive': 0.1
            }
    return params

def gen_initial(params, user_input):
    growth = 2**(1/user_input['doubling_time']) - 1
    gamma = 1/params['d_infectious']
    sigma = 1/params['d_incubation']
    pui = growth*user_input['total_confirm_cases']*params['d_test']
    i = pui*(growth + (1/params['d_test']))/gamma
    e = i*(growth + gamma)/sigma
    beta = (growth + gamma)*(growth + sigma)/sigma
    r0 =  beta/gamma
    s = user_input['regional_population'] - user_input['total_confirm_cases'] - pui - i - e

    # update params
    params['r0'] = r0
    params['n'] = user_input['regional_population']
    params['social_distancing'] = user_input['social_distancing']

    # create initial data for start date
    recover = user_input['total_confirm_cases'] - user_input['active_cases'] - user_input['death']
    initial_data = {
        'date' :user_input['start_date'],
        's': s,
        'e': e,
        'i': i,
        'pui': pui,
        'hos_mild': params['p_mild']*user_input['active_cases'], # TODO: check this ตอนแรกเยอะเกินไปหรือเปล่า
        'hos_severe':params['p_severe']*user_input['active_cases'],
        'hos_critical': params['p_critical']*user_input['active_cases'],
        'hos_fatal': params['cfr']*user_input['active_cases'],
        'home_mild': 0,
        'home_severe': 0,
        'hotel_mild': 0,
        'hotel_severe': 0,
        'r_mild_hos': params['p_mild']*recover,
        'r_mild_home': 0,
        'r_mild_hotel': 0,
        'r_severe_hos': params['p_severe']*recover,
        'r_severe_home': 0,
        'r_severe_hotel': 0,
        'r_critical_hos': (params['p_critical'] + params['cfr'])*recover,
        'death':user_input['death'],
        'new_hos_mild': 0,
        'new_hos_severe': 0,
        'new_hos_critical': 0,
        'new_pui': 0
    }

    return initial_data, params


def transform_seir(seir_df, params, hopital_market_share):
    hos_load_df = pd.DataFrame()
    hos_load_df['date'] = seir_df['date']
    hos_load_df['pt_hos_eod_mild'] = hopital_market_share * seir_df['hos_mild']
    hos_load_df['pt_hos_eod_severe'] = hopital_market_share * seir_df['hos_severe']
    hos_load_df['pt_hos_eod_critical'] = hopital_market_share * (
            seir_df['hos_critical'] + seir_df['hos_fatal'])
    hos_load_df['pt_hos_new_mild'] = hopital_market_share * seir_df['new_hos_mild']
    hos_load_df['pt_hos_new_severe'] = hopital_market_share * seir_df['new_hos_severe']
    hos_load_df['pt_hos_new_critical'] = hopital_market_share * seir_df['new_hos_critical']
    hos_load_df['pt_hos_neg_cases'] = hopital_market_share * seir_df['new_pui'] / (
            1 - params['p_test_positive'])
    hos_load_df['pt_hos_pui'] = hopital_market_share * seir_df[
        'pui'] * 1  # TODO: add parameter to adjust % of pui admit

    return hos_load_df


def project_resource(df, params):
    resources_name = [
        'icu_bed',
        'hospital_bed',
        'ppe_gloves'
    ]
    resources_df = pd.DataFrame()
    resources_df['date'] = df['date']
    # icu
    resources_df['bed_icu'] = round(df['pt_hos_eod_critical'], 0)
    resources_df['aiir'] = round(
        (df['pt_hos_eod_mild'] + df['pt_hos_eod_severe'] + df['pt_hos_eod_critical']) * params[
            'p_aiir'], 0)
    resources_df['venti'] = round(resources_df['bed_icu'] * params['p_vent'], 0)
    resources_df['ecmo'] = round(resources_df['bed_icu'] * params['p_ecmo'], 0)

    # hos
    resources_df['bed_hos'] = round(df['pt_hos_eod_severe'] + df['pt_hos_eod_mild'], 0)
    resources_df['ppe_gloves'] = round(
        df['pt_hos_eod_mild'] * 3
        + df['pt_hos_eod_severe'] * 6
        + df['pt_hos_eod_critical'] * 14
    )

    # man
    resources_df['staff_nurse_icu'] = round(
        resources_df['bed_icu'] * params['staff_nurse_icu_per_pt'] / params[
            'staff_shift_workshour'], 0)
    resources_df['staff_nurse_aid_icu'] = round(
        resources_df['bed_icu'] * params['staff_nurse_aid_icu_per_pt'] / params[
            'staff_shift_workshour'], 0)

    # material
    # favipiravir
    # chloroquine
    # test kit

    return resources_df

if __name__ == '__main__':
    sample_user_input = {
        'doubling_time': 6,
        'social_distancing': 0.5,
        'social_distancing_start': 50,
        'social_distancing_end': 80,
        'hospital_market_share': 0.5,
        'hospital_market_share': 0.5,
        'start_date': '2020-04-01',
        'steps': 300,
        'regional_population': 66000000,
        'total_confirm_cases': 1400,
        'active_cases': 1000,
        'critical_cases': 20,
        'death': 10,
    }
    event = {'body': json.dumps(sample_user_input)}
    print(hello(event, None))