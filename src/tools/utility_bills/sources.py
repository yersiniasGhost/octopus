"""
Registry of utility pre-enrollment deliveries in data/electric-bills/.

Each entry: outer zip -> inner zip member -> data file member -> parser.
member=None means "largest file inside the inner zip" (name varies).

NOTE: 'AEP-3_January 2026.zip' is CORRUPT (BadZipFile, truncated download,
verified 2026-08-19) and is excluded from jan2026 - AEP must re-send it.
NOTE: 'AEP August 2026.zip' is a mislabeled duplicate of the AES payload -
the real AEP August data is only in 'AEP August 2026x.zip'.
"""
from pathlib import Path

BILLS_DIR = Path(__file__).resolve().parents[3] / 'data' / 'electric-bills'


def _src(outer, inner_zip, member, parser, utility, opco=''):
    return dict(outer=outer, inner_zip=inner_zip, member=member,
                parser=parser, utility=utility, opco=opco)


SOURCES = {
    'aug2026': [
        _src('AEP August 2026x.zip', 'August 2026/AEP/AEPOhioPreEnrollmentList (3).zip',
             'staging/CSP_CCI.TXT', 'aep', 'AEP', 'CSP'),
        _src('AEP August 2026x.zip', 'August 2026/AEP/AEPOhioPreEnrollmentList (3).zip',
             'staging/OPCO_CCI.TXT', 'aep', 'AEP', 'OPCO'),
        _src('AES August 2026.zip', 'August 2026/AES/AES_CUSTDATA.zip',
             'Customerdata.txt', 'aes', 'AES'),
        _src('Duke August 2026.zip', 'August 2026/Duke/PreEnrollElecRes_20260719.zip',
             'Electric_Residential_20260719.csv', 'duke', 'DUKE'),
        _src('First Energy August 2026.zip', 'August 2026/FirstEnergy/cmb_ce_elig_lst_07_2026.zip',
             'cmb_ce_elig_lst_07_2026.txt', 'fe', 'FE', 'CEI'),
        _src('First Energy August 2026.zip', 'August 2026/FirstEnergy/cmb_oe_elig_lst_07_2026.zip',
             'cmb_oe_elig_lst_07_2026.txt', 'fe', 'FE', 'OE'),
        _src('First Energy August 2026.zip', 'August 2026/FirstEnergy/cmb_te_elig_lst_07_2026.zip',
             'cmb_te_elig_lst_07_2026.txt', 'fe', 'FE', 'TE'),
    ],
    'jan2026': [
        # AEP-3_January 2026.zip excluded: corrupt archive (see module docstring)
        _src('AES-3_January_2026.zip', '3_January 2026/AES/CUSTDATA.zip',
             None, 'aes', 'AES'),
        _src('Duke-3_January 2026.zip', '3_January 2026/Duke/PreEnrollElecRes_20260118.zip',
             None, 'duke', 'DUKE'),
        _src('FirstEnergy-3_January 2026.zip', '3_January 2026/First Energy/cmb_ce_elig_lst_01_2026.zip',
             None, 'fe', 'FE', 'CEI'),
        _src('FirstEnergy-3_January 2026.zip', '3_January 2026/First Energy/cmb_oe_elig_lst_01_2026.zip',
             None, 'fe', 'FE', 'OE'),
        _src('FirstEnergy-3_January 2026.zip', '3_January 2026/First Energy/cmb_te_elig_lst_01_2026.zip',
             None, 'fe', 'FE', 'TE'),
    ],
}
