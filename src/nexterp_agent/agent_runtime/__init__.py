"""Natural-language agent runtime boundaries.

This package will hold intent routing, session state, planning, tool selection,
and response generation. It must not call ERPNext/Frappe HTTP APIs directly;
all ERP execution goes through the ERPNext adapter.
"""
