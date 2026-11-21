"""Explicit Gemini API selection. Free mode never falls back to Vertex or another model."""

import os

from devfest_security.common import Blocked
from devfest_security.cost import execution_policy, require_cloud_execution
from devfest_security.free_model import verify_key_binding

DEFAULT_GEMINI_MODEL = 'gemini-4-hydrogen'


def _client_options(model):
    options = {'model': model, 'max_retries': 0, 'timeout': 45}
    if model == DEFAULT_GEMINI_MODEL:
        options.update(max_output_tokens=2048, thinking_config={'thinking_level': 'LOW'})
    else:
        options.update(temperature=1, max_output_tokens=256, thinking_config={'thinking_level': 'MINIMAL'})
    return options


def developer_chat(model, key):
    from langchain_google_genai import ChatGoogleGenerativeAI

    return ChatGoogleGenerativeAI(**_client_options(model), vertexai=False, google_api_key=key)


def vertex_expense_chat(project, account):
    from langchain_google_genai import ChatGoogleGenerativeAI

    from devfest_security.auth import operator_credentials

    return ChatGoogleGenerativeAI(
        **_client_options(DEFAULT_GEMINI_MODEL),
        vertexai=True,
        project=project,
        location='global',
        api_version='v1',
        base_url='https://aiplatform.googleapis.com',
        credentials=operator_credentials(account, project),
        additional_headers={'x-goog-user-project': project},
    )


def build_gemini(config, tools):
    if config.model == 'gemini':
        require_cloud_execution('Gemini Developer inference')
        policy = execution_policy()
        if config.gemini_model != policy.get('gemini_model') or not policy.get('model_project_unbilled'):
            raise Blocked('An explicitly verified free model project is required')
        key = os.environ.get('GEMINI_API_KEY')
        if not key:
            raise Blocked('GEMINI_API_KEY is required; do not fall back to ADC or Vertex')
        verify_key_binding(key, policy)
        chat = developer_chat(config.gemini_model, key)
    elif config.model == 'vertex':
        require_cloud_execution('Vertex inference')
        from langchain_google_genai import ChatGoogleGenerativeAI

        from devfest_security.auth import credentials

        chat = ChatGoogleGenerativeAI(**_client_options(config.gemini_model), vertexai=True,
                                      project=config.project, location=config.model_location,
                                      credentials=credentials(config.project))
    else:
        raise ValueError('Unknown live model provider')
    return chat.bind_tools([
        {'name': t['name'], 'description': t.get('description', ''), 'parameters': t['inputSchema']}
        for t in tools.values()])
