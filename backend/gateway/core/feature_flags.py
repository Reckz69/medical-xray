"""Central feature-flag access.

Feature flags let deployments enable/disable capabilities without code
changes. Flags are read from Settings (env) and can be overridden at runtime
if a dynamic store is added later.
"""

from gateway.core.config import settings


class FeatureFlags:
    @property
    def signup_enabled(self) -> bool:
        return settings.enable_signup

    @property
    def dicom_enabled(self) -> bool:
        return settings.enable_dicom

    @property
    def super_resolution_enabled(self) -> bool:
        return settings.enable_super_resolution

    @property
    def ai_report_enabled(self) -> bool:
        return settings.enable_ai_report


flags = FeatureFlags()
