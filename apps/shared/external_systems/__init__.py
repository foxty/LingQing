"""External systems bounded context: SQL data sources, HTTP API connectors, user credentials.

Submodules:
- ``domain`` — shared kernel (credential mode, purposes, ports)
- ``application`` — factories wiring credential resolver into runtime services
- ``data_source`` — connections, assets, query/discover
- ``api_connector`` — connectors, operations, HTTP execution
- ``credentials`` — BYOT user credential bindings
"""
