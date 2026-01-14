"""administrative friction metrics tracking"""
from __future__ import annotations
from pydantic import BaseModel


class FrictionMetrics(BaseModel):
    """tracks administrative friction in PA negotiations"""
    # AAV (Administrative Action Volume): discrete moves (submissions, appeals, denials, pends)
    provider_actions: int = 0
    payor_actions: int = 0

    # CPL (Clinical Probing Load): tests ordered to satisfy coverage gates
    probing_tests_count: int = 0

    # ED (Escalation Depth): 0=Approved First Try, 1=First Appeal, 2=Second Appeal, 3=Abandon
    escalation_depth: int = 0
