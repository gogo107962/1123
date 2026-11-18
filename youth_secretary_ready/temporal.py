"""Explicit Korean application times and self-reported benefit intervals."""
from datetime import date, datetime, timedelta, timezone

KST=timezone(timedelta(hours=9))


def korean_now():
    return datetime.now(KST)


def iso_date(value):
    if not isinstance(value,str):raise ValueError('YYYY-MM-DD required')
    parsed=date.fromisoformat(value)
    if parsed.isoformat()!=value:raise ValueError('Canonical YYYY-MM-DD required')
    return parsed


def aware_time(value):
    if not isinstance(value,str):raise ValueError('ISO timestamp required')
    parsed=datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:raise ValueError('Timezone offset required')
    return parsed.astimezone(KST)


def validate_application(application):
    if 'closure_notice' in application:
        notice=application['closure_notice']
        if not isinstance(notice,dict) or set(notice)!={'observed_on','source_ref','reason'}:
            raise ValueError('closure_notice requires observed_on/source_ref/reason')
        iso_date(notice['observed_on'])
        if not all(isinstance(notice[k],str) and notice[k].strip() for k in ('source_ref','reason')):
            raise ValueError('closure notice needs a source and reason')
    for key in ('open','close'):
        if application.get(key):iso_date(application[key])
    if application.get('open') and application.get('close') and application['open']>application['close']:
        raise ValueError('application dates reversed')
    if 'open_at' in application or 'close_at' in application:
        opening=aware_time(application.get('open_at'));closing=aware_time(application.get('close_at'))
        if opening>=closing:raise ValueError('application timestamps reversed or equal')
        if opening.date().isoformat()!=application.get('open') or closing.date().isoformat()!=application.get('close'):
            raise ValueError('application dates must match timestamps in Korea')


def application_period(application,at=None):
    at=korean_now() if at is None else at
    if isinstance(at,datetime):
        if at.tzinfo is None:raise ValueError('Evaluation datetime must include timezone')
        at=at.astimezone(KST)
        day=at.date()
    else:day=at
    opening=application.get('open');closing=application.get('close')
    if opening and day<iso_date(opening):return 'not_open'
    if closing and day>iso_date(closing):return 'closed'
    if application.get('closure_notice'):
        observed=iso_date(application['closure_notice']['observed_on'])
        # Observed closure date is NOT an invented effective closure date.
        # Before observation we cannot prove when the budget ran out.
        return 'closed' if day>=observed else 'unknown'
    if not opening or not closing:return 'unknown'
    if application.get('open_at') and application.get('close_at'):
        if isinstance(at,datetime):
            if at<aware_time(application['open_at']):return 'not_open'
            if at>=aware_time(application['close_at']):return 'closed'
        elif day.isoformat() in (opening,closing):
            # A historical date alone cannot establish which side of a cutoff it is.
            return 'unknown'
    return 'active'


def valid_benefit_history(value):
    if not isinstance(value,list) or len(value)>30:return False
    for record in value:
        if not isinstance(record,dict) or set(record)!={'code','start','end','ongoing'}:return False
        code=record['code']
        if not isinstance(code,str) or not 1<=len(code)<=80:return False
        if record['ongoing'] is not None and type(record['ongoing']) is not bool:return False
        try:
            start=iso_date(record['start']) if record['start'] is not None else None
            end=iso_date(record['end']) if record['end'] is not None else None
        except (ValueError,TypeError):return False
        if start and end and start>end:return False
        if record['ongoing'] is True and end is not None:return False
    return True


def benefit_active_on(records,code,reference_date,complete):
    """Closed date intervals; end is the LAST covered benefit day, not a bank deposit day.

    Positive evidence suffices. Missing dates or incomplete negative evidence stay unknown.
    ongoing=True is an explicit report of coverage through the supplied reference date.
    """
    if not valid_benefit_history(records):return None
    try:day=iso_date(reference_date)
    except (ValueError,TypeError):return None
    unknown=False
    for record in records:
        if record['code']!=code:continue
        start=iso_date(record['start']) if record['start'] else None
        end=iso_date(record['end']) if record['end'] else None
        if start and start>day:continue
        if end and end<day:continue
        if start and (end or record['ongoing'] is True):return True
        unknown=True
    return None if unknown or complete is not True else False
