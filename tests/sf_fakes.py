"""Stand-ins for the Salesforce Reports API, shaped like its real JSON responses."""
import copy
import json

# API name -> (label, data type), in the saved report's column order
COLUMNS = {
    "Lead.CreatedDate": ("Created Date", "date"),
    "Lead.Company": ("Company", "string"),
    "Lead.IsConverted": ("Converted", "boolean"),
    "Lead.Qualified__c": ("Qualified Lead", "boolean"),
    "Test_Drive__c.CreatedDate": ("Created Date", "date"),   # shown as "Test Drive Created Date"
    "Lead.Id": ("Lead ID", "id"),
}


def describe(filters=None, logic=None, aggregates=("RowCount",)):
    return {
        "reportMetadata": {
            "name": "Lead with Test ride report - After ALQ", "detailColumns": list(COLUMNS),
            "aggregates": list(aggregates), "scope": "organization",
            "reportFilters": filters or [], "reportBooleanFilter": logic, "reportFormat": "TABULAR",
            "standardDateFilter": {"column": "Lead.CreatedDate", "durationValue": "CUSTOM",
                                   "startDate": "2026-09-01", "endDate": "2026-09-30"}},
        "reportExtendedMetadata": {
            "detailColumnInfo": {k: {"label": lbl, "dataType": t} for k, (lbl, t) in COLUMNS.items()},
            "aggregateColumnInfo": {"RowCount": {"label": "Record Count"}}},
        "reportTypeMetadata": {
            "categories": [{"columns": {"Lead.CreatedDate": {"label": "Created Date"},
                                        "Lead.Status": {"label": "Lead Status"}}}],
            "scopeInfo": {"values": [{"value": "organization", "label": "All leads"}]}},
    }


def _date(iso):
    if iso is None:
        return {"value": None, "label": "-"}
    y, m, d = iso.split("-")
    return {"value": iso, "label": f"{d}/{m}/{y}"}


def row(lead_id, created="2026-10-01", test_drive=None, converted=False, company="Acme"):
    return {"dataCells": [_date(created), {"value": company, "label": company},
                          {"value": converted, "label": str(converted).lower()},
                          {"value": False, "label": "false"}, _date(test_drive),
                          {"value": lead_id, "label": lead_id}]}


def page(rows, all_data, row_count=None):
    fact = {"rows": rows}
    if row_count is not None:
        fact["aggregates"] = [{"label": f"{row_count:,}", "value": row_count}]
    return {"allData": all_data, "factMap": {"T!T": fact}}


class FakeSalesforce:
    """Answers describe, report-run and "who am I" calls; records the metadata sent with each run."""

    def __init__(self, pages, describe_json=None, viewer="Test User"):
        self.pages = list(pages)
        self.describe_json = describe_json or describe()
        self.viewer = viewer
        self.runs = []

    def restful(self, path, method="GET", params=None, data=None):
        if path.endswith("/describe"):
            return copy.deepcopy(self.describe_json)
        if path == "chatter/users/me":
            return {"name": self.viewer}
        assert method == "POST" and params == {"includeDetails": "true"}
        self.runs.append(json.loads(data)["reportMetadata"])
        return self.pages.pop(0)
