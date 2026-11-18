from pathlib import Path
from streamlit.testing.v1 import AppTest


def test_dashboard_and_region_filters():
    app = str(Path(__file__).resolve().parents[1]/'app.py')
    at = AppTest.from_file(app).run(timeout=30)
    assert not at.exception
    assert len(at.tabs)==6
    at.sidebar.multiselect[0].set_value(['СВАО']).run(timeout=30)
    assert not at.exception
    at.sidebar.multiselect[0].set_value([]).run(timeout=30)
    assert not at.exception
