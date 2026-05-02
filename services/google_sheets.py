import json
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']


def _get_service(credentials_json):
    info = json.loads(credentials_json)
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    return build('sheets', 'v4', credentials=creds)


def get_sheet_availability(credentials_json, sheet_id):
    """
    Read coach availability from the 'Coach Availability' sheet.
    Returns a list of dicts: {coach, mon, tue, wed, thu, fri}
    """
    if not credentials_json:
        return []

    try:
        service = _get_service(credentials_json)
        result = service.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range='Coach Availability!A1:G20'
        ).execute()
        rows = result.get('values', [])

        # Find header row (row with 'Coach' in first column)
        header_idx = None
        for i, row in enumerate(rows):
            if row and row[0].strip() == 'Coach':
                header_idx = i
                break

        if header_idx is None:
            return []

        availability = []
        for row in rows[header_idx + 1:]:
            if not row or not row[0].strip():
                continue
            coach_name = row[0].strip()
            if coach_name.lower() in ('key', 'notes:', ''):
                break
            availability.append({
                'coach': coach_name,
                'mon': row[1].strip() if len(row) > 1 else '',
                'tue': row[2].strip() if len(row) > 2 else '',
                'wed': row[3].strip() if len(row) > 3 else '',
                'thu': row[4].strip() if len(row) > 4 else '',
                'fri': row[5].strip() if len(row) > 5 else '',
                'sat': row[6].strip() if len(row) > 6 else '',
            })
        return availability

    except Exception as e:
        print(f'Google Sheets error: {e}')
        return []
