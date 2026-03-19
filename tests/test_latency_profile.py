import statistics
import time


def test_latency_profile():

    latencies = []

    for _ in range(100):

        start = time.perf_counter()

        time.sleep(0.002)

        end = time.perf_counter()

        latencies.append(end - start)

    avg_latency = statistics.mean(latencies)

    assert avg_latency < 0.01