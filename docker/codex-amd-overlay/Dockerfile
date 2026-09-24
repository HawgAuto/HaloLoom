# Local candidate overlay only; BASE_IMAGE must be an inspected local tag.
ARG BASE_IMAGE
FROM ${BASE_IMAGE}
USER root

# The context carries a complete, offline Git bundle rather than a tree export.
# Cloning it preserves the commit object and makes verify_ecosystem.py capable
# of binding the installed source to the exact candidate GEAK revision.
COPY GEAK.bundle /opt/haloloom/source-current/GEAK.bundle
RUN set -eux; \
    rm -rf /opt/haloloom/components/GEAK; \
    git clone --no-local /opt/haloloom/source-current/GEAK.bundle /opt/haloloom/components/GEAK; \
    git -C /opt/haloloom/components/GEAK checkout --detach cd1af9459f00d3d785978852c2b3399e90d72853; \
    test "$(git -C /opt/haloloom/components/GEAK rev-parse HEAD)" = "cd1af9459f00d3d785978852c2b3399e90d72853"; \
    test "$(git -C /opt/haloloom/components/GEAK rev-parse HEAD^{tree})" = "7cf54b78f58449ecdaa8f0504adf0b5d7434fd1b"; \
    git -C /opt/haloloom/components/GEAK diff --quiet; \
    git -C /opt/haloloom/components/GEAK diff --cached --quiet; \
    chown -R 1000:1000 /opt/haloloom/components/GEAK; \
    git config --system --add safe.directory /opt/haloloom/components/GEAK

# This verifier differs from the inherited release verifier only in the exact
# GEAK candidate ref. All other source, import, command and runner gates remain.
COPY verify_ecosystem.py /opt/haloloom/verify_ecosystem.py
LABEL haloloom.geak_ref="cd1af9459f00d3d785978852c2b3399e90d72853" \
      haloloom.geak_tree="7cf54b78f58449ecdaa8f0504adf0b5d7434fd1b" \
      haloloom.promotion_authority="false"
USER 1000:1000
RUN /opt/venv/bin/python3 /opt/haloloom/verify_ecosystem.py
