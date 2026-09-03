import pytest
from octodns.record import Record
from octodns.zone import Zone


@pytest.fixture(autouse=True)
def default_validators():
    """Reset octodns validator registry to its default set, Managers built in other tests may have changed it."""

    Record.enable_validators(("legacy",))
    Zone.enable_zone_validators(("legacy",))
