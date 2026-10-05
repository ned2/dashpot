"""Install, check, and describe each harness's lifecycle hook integration.

``registry`` says what each harness's integration installs and where. A
hook installer writes the hooks themselves: ``hooks_file`` for Codex and
Claude Code, ``opencode_plugin`` for OpenCode. ``skill_copies`` and
``agent_copies`` manage the bundled skills and agents, ``harness`` runs one
harness's installation, removal and report, and ``across`` runs several in
one command. ``arguments`` refuses the command's conflicting arguments and
totals its harnesses' reports. ``diagnostics`` reports the session records
and claimed identity ``--status`` closes with.
"""

from .across import INTEGRATION_ORDER as INTEGRATION_ORDER
from .across import CombinedStatus as CombinedStatus
from .across import HarnessOutcome as HarnessOutcome
from .across import HarnessReport as HarnessReport
from .across import in_integration_order as in_integration_order
from .across import install_integrations as install_integrations
from .across import integrations_status as integrations_status
from .across import refresh_integrations as refresh_integrations
from .agent_copies import agent_file as agent_file
from .arguments import IntegrationTotals as IntegrationTotals
from .arguments import integration_totals as integration_totals
from .arguments import refuse_integrate_arguments as refuse_integrate_arguments
from .harness import IntegrationPresence as IntegrationPresence
from .harness import IntegrationState as IntegrationState
from .harness import install_integration as install_integration
from .harness import integration_presence as integration_presence
from .harness import integration_status as integration_status
from .harness import remove_integration as remove_integration
from .registry import BUNDLED_AGENTS as BUNDLED_AGENTS
from .registry import BUNDLED_AGENTS_ROOT as BUNDLED_AGENTS_ROOT
from .registry import BUNDLED_SKILL_VERSION as BUNDLED_SKILL_VERSION
from .registry import BUNDLED_SKILLS as BUNDLED_SKILLS
from .registry import BUNDLED_SKILLS_ROOT as BUNDLED_SKILLS_ROOT
from .registry import INTEGRATIONS as INTEGRATIONS
from .registry import ISSUE_WORK_SKILL as ISSUE_WORK_SKILL
from .registry import WORKER_AGENT as WORKER_AGENT
from .registry import BundledAgent as BundledAgent
from .registry import BundledSkill as BundledSkill
from .registry import ConfigurationDirectory as ConfigurationDirectory
from .registry import HarnessIntegration as HarnessIntegration
from .registry import configuration_directory as configuration_directory
from .registry import integration as integration
from .registry import resolve_hook_command as resolve_hook_command
from .skill_copies import skill_directory as skill_directory
from .writes import IncompleteIntegrationError as IncompleteIntegrationError
from .writes import IncompleteRemovalError as IncompleteRemovalError
from .writes import IntegrationError as IntegrationError
