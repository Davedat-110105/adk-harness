from adk_harness.cloud.entrypoints import receiver_entrypoint, worker_main


def test_cloud_entrypoints_are_importable_and_callable() -> None:
    assert callable(receiver_entrypoint)
    assert callable(worker_main)
