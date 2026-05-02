FROM n8nio/n8n:latest

USER root

RUN apk add --no-cache python3 py3-pip curl bash \
  && python3 -m venv /opt/meta_ads_agent_venv \
  && /opt/meta_ads_agent_venv/bin/pip install --no-cache-dir openai requests

COPY scripts /opt/meta_ads_n8n_agent/scripts
RUN chmod +x /opt/meta_ads_n8n_agent/scripts/*.py \
  && mkdir -p /data/meta_ads_agent_pending \
  && chown -R node:node /opt/meta_ads_n8n_agent /data/meta_ads_agent_pending

ENV PATH="/opt/meta_ads_agent_venv/bin:${PATH}"
ENV META_AGENT_PENDING_DIR="/data/meta_ads_agent_pending"
ENV META_AGENT_DATE_PRESET="last_7d"
ENV META_AGENT_MODEL="gpt-4.1-mini"
ENV META_AD_ACCOUNT_ID="act_2073150323260144"
ENV TELEGRAM_CHAT_ID="1327792194"
ENV META_EXECUTION_MODE="dry_run"

USER node
