import pytest

from app.capacity import EndpointCapacity


@pytest.mark.parametrize(
    "active,expected", [(0, True), (1, True), (2, False), (3, False)]
)
def test_capacity_at_slot_boundary(active: int, expected: bool):
    capacity = EndpointCapacity(max_concurrent=2, max_queue=3, active=active)
    assert capacity.has_capacity() is expected


@pytest.mark.parametrize(
    "queued,expected", [(0, True), (2, True), (3, False), (4, False)]
)
def test_queue_at_limit(queued: int, expected: bool):
    capacity = EndpointCapacity(max_concurrent=2, max_queue=3, queue_size=queued)
    assert capacity.has_queue_room() is expected


def test_default_latency_before_samples():
    capacity = EndpointCapacity(max_concurrent=2, max_queue=3)
    assert capacity.avg_latency_ms() == 500.0
    assert capacity.estimated_wait_ms(position=4) == 1000


def test_recorded_latency_is_averaged_in_milliseconds():
    capacity = EndpointCapacity(max_concurrent=2, max_queue=3)
    capacity.record_latency(0.2)
    capacity.record_latency(0.4)
    assert capacity.avg_latency_ms() == pytest.approx(300.0)


@pytest.mark.parametrize(
    "concurrent,position,expected",
    [(2, 1, 400), (2, 2, 400), (2, 3, 600), (2, 6, 1200), (0, 2, 800)],
)
def test_wait_estimate_uses_queue_position_and_concurrency(
    concurrent: int, position: int, expected: int
):
    capacity = EndpointCapacity(max_concurrent=concurrent, max_queue=6)
    capacity.record_latency(0.4)
    assert capacity.estimated_wait_ms(position) == expected


@pytest.mark.parametrize(
    "active,queued,accepting",
    [(0, 0, True), (1, 3, True), (2, 2, True), (2, 3, False)],
)
def test_status_reports_limits_counts_and_accepting(
    active: int, queued: int, accepting: bool
):
    capacity = EndpointCapacity(
        max_concurrent=2, max_queue=3, active=active, queue_size=queued
    )
    capacity.record_latency(0.12345)
    assert capacity.status_dict() == {
        "active": active,
        "max_concurrent": 2,
        "queued": queued,
        "max_queue": 3,
        "accepting": accepting,
        "avg_latency_ms": 123.5,
    }


def test_wait_counts_down_with_the_running_jobs():
    """With start times known, position 1 waits for the job that has run the
    longest, not for a whole average."""
    capacity = EndpointCapacity(max_concurrent=2, max_queue=6)
    capacity.record_latency(30.0)
    capacity.job_started(100.0)
    capacity.job_started(110.0)
    # at t=120 the first job has 10 s left on average, the second 20 s
    assert capacity.estimated_wait_ms(1, now=120.0) == 10_000
    assert capacity.estimated_wait_ms(2, now=120.0) == 20_000
    # position 3 waits for a slot to free twice
    assert capacity.estimated_wait_ms(3, now=120.0) == 40_000


def test_a_job_past_the_average_is_taken_for_a_long_one():
    """Short texts pull the average down; a job well past it is a long text,
    so it gets half its elapsed time, not a sliver of the average."""
    capacity = EndpointCapacity(max_concurrent=1, max_queue=6)
    capacity.record_latency(20.0)
    capacity.job_started(0.0)
    assert capacity.estimated_wait_ms(1, now=60.0) == 30_000
    assert capacity.estimated_wait_ms(1, now=22.0) == 11_000


def test_finished_jobs_leave_the_estimate():
    capacity = EndpointCapacity(max_concurrent=2, max_queue=6)
    capacity.record_latency(10.0)
    capacity.job_started(5.0)
    capacity.job_finished(5.0)
    assert capacity.estimated_wait_ms(1, now=6.0) == 10_000
