import pandas as pd
import numpy as np


# Data preparation

def get_resource_consumption():
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
        # drug
        'favipiravir_first_used': 8,
        'faviriravir_census_used': 3,

    }
    return resource_consumption


def transform_seir(seir_df, params, hopital_market_share):
    hos_load_df = pd.DataFrame()
    hos_load_df['date'] = seir_df['date']
    hos_load_df['pt_hos_eod_mild'] = hopital_market_share * seir_df['hos_mild']
    hos_load_df['pt_hos_eod_severe'] = hopital_market_share * \
                                       seir_df['hos_severe']
    hos_load_df['pt_hos_eod_critical'] = hopital_market_share * (
            seir_df['hos_critical'] + seir_df['hos_fatal'])
    hos_load_df['pt_hos_new_mild'] = hopital_market_share * \
                                     seir_df['new_hos_mild']
    hos_load_df['pt_hos_new_severe'] = hopital_market_share * \
                                       seir_df['new_hos_severe']
    hos_load_df['pt_hos_new_critical'] = hopital_market_share * \
                                         seir_df['new_hos_critical']
    hos_load_df['pt_hos_neg_cases'] = hopital_market_share * seir_df['new_pui'] / (
            1 - params['p_test_positive'])
    hos_load_df['pt_hos_pui'] = hopital_market_share * seir_df[
        'pui'] * 1  # TODO: add parameter to adjust % of pui admit

    return hos_load_df


def project_resource(df, resource_consumption=get_resource_consumption()):
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
        (df['pt_hos_eod_mild'] + df['pt_hos_eod_severe'] + df['pt_hos_eod_critical']) * resource_consumption[
            'p_aiir'], 0)
    resources_df['venti'] = round(
        resources_df['bed_icu'] * resource_consumption['p_vent'], 0)
    resources_df['ecmo'] = round(resources_df['bed_icu'] * resource_consumption['p_ecmo'], 0)

    # hos
    resources_df['bed_hos'] = round(
        df['pt_hos_eod_severe'] + df['pt_hos_eod_mild'], 0)

    # man
    resources_df['staff_nurse_icu'] = round(
        resources_df['bed_icu'] * resource_consumption['staff_nurse_icu_per_pt'] / resource_consumption[
            'staff_shift_workshour'], 0)
    resources_df['staff_nurse_aid_icu'] = round(
        resources_df['bed_icu'] * resource_consumption['staff_nurse_aid_icu_per_pt'] / resource_consumption[
            'staff_shift_workshour'], 0)

    # material
    # TODO: resources_df['ppe_mask']
    # TODO: resources_df['ppe_cover_all']
    resources_df['ppe_gloves'] = round(
        df['pt_hos_eod_mild'] * 3
        + df['pt_hos_eod_severe'] * 6
        + df['pt_hos_eod_critical'] * 14
    )
    # favipiravir
    resources_df['drug_favipiravir_first_dose'] = resource_consumption['favipiravir_first_used'] * (
            df['pt_hos_new_severe'] + df['pt_hos_new_critical'])
    s_cumsum = df['pt_hos_new_severe'].cumsum()
    s_diff = pd.Series([0] * 5).append(s_cumsum)[:len(s_cumsum)].reset_index(drop=True)
    df['pt_hos_severe_first_5day'] = s_cumsum - s_diff
    s_cumsum = df['pt_hos_new_critical'].cumsum()
    s_diff = pd.Series([0] * 10).append(s_cumsum)[:len(s_cumsum)].reset_index(drop=True)
    df['pt_hos_critical_first_10day'] = s_cumsum - s_diff
    resources_df['drug_favipiravir_census_dose'] = resource_consumption['faviriravir_census_used'] * (
            df['pt_hos_severe_first_5day'] + df['pt_hos_critical_first_10day'])
    resources_df['drug_favipiravir'] = resources_df['drug_favipiravir_first_dose'] + resources_df[
        'drug_favipiravir_census_dose']
    # chloroquine
    # test kit

    return resources_df
