from __future__ import annotations

import itertools

from locust import HttpUser, between, task


class OperatorSmokeUser(HttpUser):
    wait_time = between(0.5, 2)
    _ids = itertools.count(1)

    def on_start(self) -> None:
        self.headers = {
            "x-actor-id": f"load-manager-{next(self._ids)}",
            "x-actor-role": "manager",
        }

    @task(5)
    def health(self) -> None:
        self.client.get("/health")

    @task(3)
    def jobs(self) -> None:
        self.client.get("/jobs?limit=20", headers=self.headers)

    @task(2)
    def alerts(self) -> None:
        self.client.get("/alerts?limit=20", headers=self.headers)

    @task(2)
    def operations_summary(self) -> None:
        self.client.get("/operations/summary", headers=self.headers)

    @task(1)
    def evaluations(self) -> None:
        self.client.get("/evaluations?limit=20", headers=self.headers)
