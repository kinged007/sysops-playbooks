#!/usr/bin/env bash
# Read-only AWS diagnostics — safe on any host, no writes, no secrets printed.
# Usage: bash .agents/skills/aws-management/scripts/aws-doctor.sh [--profile PROFILE] [--region REGION]
set -uo pipefail

PROFILE="${1:-}"
REGION="${2:-}"
# also accept --profile / --region flags
while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile) PROFILE="$2"; shift 2 ;;
    --region)  REGION="$2"; shift 2 ;;
    *) shift ;;
  esac
done

PROFILE_ARGS=()
REGION_ARGS=()
[[ -n "$PROFILE" ]] && PROFILE_ARGS=(--profile "$PROFILE")
[[ -n "$REGION"  ]] && REGION_ARGS=(--region "$REGION")

pass() { echo "  [OK] $*"; }
warn() { echo "  [WARN] $*"; }
fail() { echo "  [FAIL] $*"; }
info() { echo "  [INFO] $*"; }

echo "== AWS doctor (read-only) =="
[[ -n "$PROFILE" ]] && info "profile: $PROFILE" || info "profile: (default)"
[[ -n "$REGION"  ]] && info "region: $REGION"

echo ""
echo "-- CLI --"
if command -v aws >/dev/null 2>&1; then
  pass "aws found: $(aws --version 2>&1)"
  echo "       which: $(command -v aws)"
else
  fail "aws not found on PATH — run scripts/install-aws-cli.sh"
fi

if command -v jq >/dev/null 2>&1; then
  pass "jq found: $(jq --version 2>&1)"
else
  warn "jq not found — JSON output will be raw (sudo apt-get install -y jq)"
fi

echo ""
echo "-- Config --"
if command -v aws >/dev/null 2>&1; then
  # shellcheck disable=SC2068
  aws configure list ${PROFILE_ARGS[@]+"${PROFILE_ARGS[@]}"} 2>&1 | sed 's/^/       /' || warn "aws configure list failed"
  echo "       config file: ~/.aws/config"
  if [[ -f ~/.aws/config ]]; then
    # redact sso / account values
    sed -E 's/(sso_start_url|sso_account_id|sso_role_name|role_arn).*/\1 = <redacted>/' ~/.aws/config | sed 's/^/       /'
  else
    warn "~/.aws/config not found"
  fi
fi

echo ""
echo "-- Identity --"
if command -v aws >/dev/null 2>&1; then
  id_out="$(aws sts get-caller-identity ${PROFILE_ARGS[@]+"${PROFILE_ARGS[@]}"} --output json 2>&1)" || true
  if echo "$id_out" | grep -q '"Account"'; then
    pass "sts get-caller-identity succeeded"
    echo "$id_out" | sed 's/^/       /'
  else
    fail "sts get-caller-identity failed:"
    echo "$id_out" | sed 's/^/       /'
    if echo "$id_out" | grep -q "ExpiredToken\|TokenRefreshRequired"; then
      info "hint: aws sso login --profile $PROFILE"
    fi
    if echo "$id_out" | grep -q "InvalidClientTokenId"; then
      info "hint: check ~/.aws/credentials or SSO cache for profile $PROFILE"
    fi
  fi
fi

echo ""
echo "-- Region --"
if command -v aws >/dev/null 2>&1; then
  # shellcheck disable=SC2068
  reg="$(aws configure get region ${PROFILE_ARGS[@]+"${PROFILE_ARGS[@]}"} 2>&1)" || reg=""
  if [[ -n "$reg" && "$reg" != *"not found"* ]]; then
    pass "region: $reg"
  else
    warn "region not set for profile ${PROFILE:-(default)} — set with: aws configure set --profile ${PROFILE:-default} region <AWS_REGION>"
  fi
  # quick AZ check (needs ec2:DescribeAvailabilityZones)
  az_out="$(aws ec2 describe-availability-zones ${PROFILE_ARGS[@]+"${PROFILE_ARGS[@]}"} ${REGION_ARGS[@]+"${REGION_ARGS[@]}"} --output text --query 'AvailabilityZones[0].RegionName' 2>&1)" || true
  if [[ -n "$az_out" && "$az_out" != *"UnauthorizedOperation"* && "$az_out" != *"AccessDenied"* ]]; then
    pass "AZ check: $az_out"
  else
    info "AZ check skipped/denied (needs ec2:DescribeAvailabilityZones): $az_out"
  fi
fi

echo ""
echo "-- Network --"
if command -v curl >/dev/null 2>&1; then
  region_for_url="${REGION:-us-east-1}"
  if curl -Is --max-time 5 "https://sts.${region_for_url}.amazonaws.com" 2>&1 | head -n 1 | grep -q "200\|400\|403"; then
    pass "egress to sts.${region_for_url}.amazonaws.com reachable"
  else
    warn "egress check to sts.${region_for_url}.amazonaws.com failed — check proxy/VPN/firewall"
    env | grep -i -E 'proxy|no_proxy' | sed 's/^/       /' || true
  fi
else
  warn "curl not found — skipping egress check"
fi

echo ""
echo "Done. Fix WARN/FAIL items above, then re-run."
echo "Next: fill runs/aws-management[-<suffix>]/inventory.md and plan.md per the skill."
