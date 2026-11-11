"""Stable business names for the one current implementation of each structure.

Each name identifies a business structure of the current code — there is no
implementation generation, no version selection and no legacy alternative.
Historical records keep their original bytes; this module never interprets
them.
"""

# Strategy 1 conditional-plan task protocol.
PLAN_PROTOCOL = 'conditional-plan'
# The single current ending policy: complete original goal, >=5 effective
# steps, no cumulative ceiling, sealed evidence.
ENDING_POLICY = 'goal-completion-ending'
# Strategy-1 native ReAct decision loop and observation references.
REACT_PROTOCOL = 'react-native'
REFERENCE_PROTOCOL = 'request-observation-ref'
EFFECTIVE_ACTION_RULE = 'effective-actions-dynamic-regions'
NAVIGATION_PROTOCOL = 'observed-navigation'
DELAYED_NAVIGATION_PROTOCOL = 'explicit-href-landing'
PLANNING_INTENT_PROTOCOL = 'planning-intent'
READING_PROGRESS_PROTOCOL = 'reading-progress'
READING_PROGRESS_END = 'five-effective-visible-ending'
# Result routes shared by both collection strategies.
RESULT_EXECUTION_POLICY = 'result-execution'
RESULT_COMPLETION_PROTOCOL = 'result-completion'
READING_PLAN_COMPLETION_POLICY = 'reading-plan-completion'
PLAN_EXECUTION_POLICY = 'plan-execution'
PLAN_WAIT_EXECUTION_POLICY = 'plan-wait-execution'
NUMERIC_RESULT_EVIDENCE_POLICY = 'numeric-result-evidence'
# Completion verifiers.
WIKI_READING_COMPLETION = 'wiki-reading-completion'
DIRECT_ARTICLE_PROTOCOL = 'direct-article-reading'
DIRECT_COMPLETION_PROTOCOL = 'direct-reading-completion'
GOAL_EVIDENCE_PROTOCOL = 'goal-evidence'
PLAN_FACTS_PROTOCOL = 'plan-facts'
# Host-side observation and evidence pipelines.
TRUSTED_PREFIX_POLICY = 'trusted-prefix'
ACTION_STABILITY_PROTOCOL = 'action-scoped-evidence'
BROWSER_STABILITY_RULE = 'related-stability'
CAPTURE_PROTOCOL = 'capture'
DYNAMIC_REGIONS_PROTOCOL = 'dynamic-regions'
DYNAMIC_REGION_STABILITY = 'dynamic-region-stability'
SEARCH_SUGGESTIONS_PROTOCOL = 'search-suggestions'
SESSION_OBJECTIVE_PROTOCOL = 'session-objective'
REACT_SESSION_PROTOCOL = 'react-session'
FRAGMENT_POLICY = 'legal-web-actions'
