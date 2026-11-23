import os

# Keep the incident history in memory during tests (never touch data/incidents.json).
os.environ["FIRESIM_INCIDENTS_FILE"] = ":memory:"
