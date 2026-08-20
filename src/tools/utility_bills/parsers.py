"""
Parsers for the four utility pre-enrollment list formats. Each parser takes an
iterator of text lines and yields AccountRecord. Only period-end date + billed
kWh are captured (kW demand etc. available in source, deliberately dropped).

Format specs (shipped inside the deliveries):
  AEP  - 'staging/OHPreEnrollList Data Format.xlsx' (fixed-width, 1100 bytes)
  AES  - 'PRE_ENROLLMENT_LIST_Specs.pdf' (comma-delimited, no header)
  Duke - 'Elec Pre-enrollment list structure-new*.doc' (CSV with header)
  FE   - header row embedded in each ']'-delimited file
"""
import csv
import re

from .record import AccountRecord

DATE_MDY = re.compile(r'^(\d{2})/(\d{2})/(\d{4})$')
DATE_ISO = re.compile(r'^\d{4}-\d{2}-\d{2}$')


def _mdy(s):
    m = DATE_MDY.match(s.strip())
    return f"{m.group(3)}-{m.group(1)}-{m.group(2)}" if m else None


def _ymd8(s):
    s = s.strip()
    if len(s) == 8 and s.isdigit() and s != '00000000':
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"
    return None


def _num(s):
    s = s.strip().lstrip('+')
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_aep(lines, operating_co=''):
    """Fixed-width: hdr fields end at byte 333, then 12 x (from 10, to 10, kWh 10, kW 15)."""
    for line in lines:
        if not line.startswith('2'):        # '1'=header, '9'=trailer
            continue
        name = line[9:44].strip()
        addr1, addr2 = line[44:99].strip(), line[99:154].strip()
        city, state = line[154:174].strip(), line[174:176].strip()
        zip5 = line[176:181].strip()
        readings = []
        for i in range(12):
            off = 333 + i * 45
            to_date = line[off + 10:off + 20].strip()
            kwh = _num(line[off + 20:off + 30])
            if DATE_ISO.match(to_date) and kwh is not None:
                readings.append((to_date, kwh))
        yield AccountRecord('AEP', operating_co, '', name,
                            (addr1 + ' ' + addr2).strip(), city, state, zip5, readings)


def parse_aes(lines, operating_co=''):
    """Comma-delimited, no header. Leading account field, then spec fields:
    MA (mailing) block f1-6, SA (service) block f7-12, meta f13-23,
    then 12 x 10-field usage groups starting at f24 (date, kWh, 8 unused)."""
    for line in lines:
        f = line.rstrip('\n').split(',')
        if len(f) < 34:
            continue
        start = 24
        if not DATE_MDY.match(f[start].strip()):    # comma-in-name shifted the row
            cand = [i for i in range(20, min(len(f), 40)) if DATE_MDY.match(f[i].strip())]
            if not cand:
                continue
            start = cand[0]
        shift = start - 24
        def g(i):
            return f[i + shift].strip() if i + shift < len(f) else ''
        street, unit = g(9), g(10)
        addr = (street + ' ' + unit).strip() if unit else street
        city_st = g(11)
        m = re.match(r'^(.*)\s+(OH|KY|IN)\s*$', city_st.upper().split(' 4')[0].strip())
        city = m.group(1) if m else city_st
        state = m.group(2) if m else 'OH'
        zp = g(12)
        zip5 = zp[:5] if re.match(r'^\d{5}', zp) else ''
        if not zip5:
            mz = re.search(r'(\d{5})(-\d{0,4})?\s*$', city_st)
            zip5 = mz.group(1) if mz else ''
        readings = []
        for i in range(start, len(f) - 1, 10):
            d, kwh = _mdy(f[i]), _num(f[i + 1]) if i + 1 < len(f) else None
            if d and kwh is not None:
                readings.append((d, kwh))
        yield AccountRecord('AES', operating_co, f[0].strip(), g(7) or g(1),
                            addr, city.strip(), state, zip5, readings)


def parse_duke(lines, operating_co=''):
    """CSV with header (utf-8 BOM). 12 x (Billed_Kwh{i}, Billed_Kw{i}, METERDATE{i}, ...)."""
    for row in csv.DictReader(lines):
        addr = f"{(row.get('House_Address') or '').strip()} {(row.get('Service_Street_Address') or '').strip()}".strip()
        readings = []
        for i in range(1, 13):
            # period 1 is 'METERDATE1'; periods 2-12 leak the raw Oracle alias
            d = _mdy(row.get(f'METERDATE{i}')
                     or row.get(f'TO_CHAR_Meter_Reading_Date{i}__mm_dd_yyyy__') or '')
            kwh = _num(row.get(f'Billed_Kwh{i}') or '')
            if d and kwh is not None:
                readings.append((d, round(kwh, 1)))
        yield AccountRecord('DUKE', operating_co, '', (row.get('BUSINESS_PARTNER') or '').strip(),
                            addr, (row.get('Service_City') or '').strip(),
                            (row.get('Service_State') or '').strip(),
                            (row.get('Service_Zip_Code') or '').strip()[:5], readings)


def parse_firstenergy(lines, operating_co=''):
    """']'-delimited with header. f0 company, f1 acct, f2 name, f4 addr, f5 city,
    f6 st, f7 zip, meta f8-20, then 12 x (LRDDTES yyyymmdd, kWh, demand) from f21."""
    first = True
    for line in lines:
        if first:
            first = False
            continue
        f = line.rstrip('\n').split(']')
        if len(f) < 24:
            continue
        readings = []
        for i in range(21, min(len(f) - 1, 21 + 36), 3):
            d, kwh = _ymd8(f[i]), _num(f[i + 1])
            if d and kwh is not None:
                readings.append((d, kwh))
        yield AccountRecord('FE', operating_co or f[0].strip(), f[1].strip(), f[2].strip(),
                            f[4].strip(), f[5].strip(), f[6].strip(), f[7].strip()[:5], readings)


PARSERS = {'aep': parse_aep, 'aes': parse_aes, 'duke': parse_duke, 'fe': parse_firstenergy}
