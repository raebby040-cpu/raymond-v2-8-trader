# Minimal smoke test so pytest has at least one test to run.
# Keeps CI from failing with "collected 0 items" when there are no other tests yet.

def test_smoke():
    assert True
