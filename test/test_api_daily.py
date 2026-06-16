import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from main import api_app, SessionLocal, Post
from datetime import datetime, timedelta

client = TestClient(api_app)

def test_daily_complaints():
    """
    Test that /api/complaints/daily:
    - returns HTTP 200
    - returns at most 30 entries
    - each entry has 'date', 'threads', 'jira', 'app_store' keys
    - date is in 'DD MM YYYY' format (space-separated, zero-padded)
    """
    # Use a far-future date that is certain to be in the 30 most recent
    # We use today+1000 days to be safely in the future but within datetime range
    future_date = datetime.utcnow() + timedelta(days=1000)
    # Clamp to a realistic year to avoid DB issues
    test_dt = future_date.replace(hour=12, minute=0, second=0, microsecond=0)
    test_dt2 = test_dt + timedelta(days=1)

    db = SessionLocal()
    try:
        # Upsert dummy posts
        exists1 = db.query(Post).filter(Post.post_hash_id == "dummy_test_hash_1").first()
        exists2 = db.query(Post).filter(Post.post_hash_id == "dummy_test_hash_2").first()

        if exists1:
            # Update to correct test date in case stale data exists
            exists1.posted_at = test_dt
            exists1.crawled_at = test_dt
        else:
            db.add(Post(
                post_hash_id="dummy_test_hash_1",
                platform="threads",
                posted_at=test_dt,
                crawled_at=test_dt,
            ))

        if exists2:
            exists2.posted_at = test_dt2
            exists2.crawled_at = test_dt2
        else:
            db.add(Post(
                post_hash_id="dummy_test_hash_2",
                platform="jira",
                posted_at=test_dt2,
                crawled_at=test_dt2,
            ))

        db.commit()
    except Exception as e:
        db.rollback()
        raise RuntimeError(f"Failed to set up test data: {e}")
    finally:
        db.close()

    response = client.get("/api/complaints/daily")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) <= 30

    expected_date1 = test_dt.strftime("%d %m %Y")
    expected_date2 = test_dt2.strftime("%d %m %Y")

    found_1 = False
    found_2 = False
    for entry in data:
        assert "date" in entry
        assert "threads" in entry
        assert "jira" in entry
        assert "app_store" in entry

        # Date should be in dd mm yyyy format (space-separated, zero-padded)
        parts = entry["date"].split()
        assert len(parts) == 3, f"Expected 3 parts in date '{entry['date']}', got {len(parts)}"
        assert len(parts[0]) == 2, f"Day part '{parts[0]}' should be 2 chars (zero-padded)"
        assert len(parts[1]) == 2, f"Month part '{parts[1]}' should be 2 chars (zero-padded)"
        assert len(parts[2]) == 4, f"Year part '{parts[2]}' should be 4 chars"

        if entry["date"] == expected_date1:
            found_1 = True
        if entry["date"] == expected_date2:
            found_2 = True

    assert found_1, f"Expected test date '{expected_date1}' not found in response: {[e['date'] for e in data]}"
    assert found_2, f"Expected test date '{expected_date2}' not found in response: {[e['date'] for e in data]}"

    # Clean up test data
    db = SessionLocal()
    try:
        db.query(Post).filter(Post.post_hash_id.in_(["dummy_test_hash_1", "dummy_test_hash_2"])).delete(synchronize_session=False)
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()
