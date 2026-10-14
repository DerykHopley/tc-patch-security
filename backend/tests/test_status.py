"""Open, accepted and review due at the as-of date (seam 2, a pure function). Check ids: A16b.n, from #27."""
import pytest

from app.status import is_open, review_due

AS_OF = "2026-10-13"


# status, review date, as-of → open?, review due?
@pytest.mark.parametrize("status,review_date,as_of,open_,due", [
    ("open", None, AS_OF, True, False),
    ("fixed", None, AS_OF, False, False),
    ("not_affected", None, AS_OF, False, False),
    ("not_watched", None, AS_OF, False, False),
    ("accepted", "2027-01-11", AS_OF, False, False),  # before the review date: not open
    ("accepted", "2026-10-14", AS_OF, False, False),  # the day before
    ("accepted", "2026-10-13", AS_OF, True, True),  # on the review date: review due, back in the open list
    ("accepted", "2026-09-01", AS_OF, True, True),  # after it
    ("accepted", None, AS_OF, True, True),  # a hand-edited file without a review date: due now, never hidden
    ("fixed", "2026-09-01", AS_OF, False, False),  # a review date only counts for accepted
])
def test_a16b_1_open_accepted_and_review_due_at_the_as_of_date(status, review_date, as_of, open_, due):
    assert is_open(status, review_date, as_of) is open_
    assert review_due(status, review_date, as_of) is due
