"""Thin client for the Uzio onboarding-service (production) API.

Replicates the "Prod-Amazon Onboarding Automation" Postman collection: login to get
a JWT, then push files to the vendor-agnostic Employee Census endpoint. Scope is
intentionally limited to Employee Census for now -- the same login() can be reused
to wire the remaining endpoints (tax withholding, payment method, deductions,
contributions, workers comp, SOC code, prior payroll, job title) later.

The push response only carries COUNTS (TotalMap / SuccessMap / FailureMap). The
per-employee errors and warnings are written to that run's row in
onboarding_automation_history, so after a push we read that one row back through
the read-only /app/onboarding/query endpoint (PHIX-98714) with the same JWT.

Credentials are never persisted: login() takes them as plain arguments and the
JWT lives only for the duration of the button click. session_state keeps the
push response and the run's error rows so they survive reruns -- nothing else.
"""
import json
import time

import pandas as pd
import requests
import streamlit as st

from utils.ui_components import _callout

DEFAULT_PROD_HOST = "https://app.uzio.com"

# Only the id is interpolated, and only after int() -- this is never free-form SQL.
RUN_LOG_SQL = ("select id, start_time, end_time, error_messages, optional_validations "
               "from onboarding_automation_history where id = {run_id:d}")


class OnboardingAPIError(Exception):
    """Raised when the onboarding API rejects a login or returns an unusable response."""


def login(username: str, password: str, fein: str, vendor: str,
          prod_host: str = DEFAULT_PROD_HOST, timeout: int = 30) -> str:
    """POST {prod_host}/app/onboarding/token -> JWT string.

    vendor must match the source census's vendor: "ADP" or "PAYCOM".
    """
    url = f"{prod_host.rstrip('/')}/app/onboarding/token"
    payload = {"username": username, "password": password, "fein": fein, "vendor": vendor}
    try:
        resp = requests.post(url, json=payload, timeout=timeout)
    except requests.RequestException as e:
        raise OnboardingAPIError(f"Could not reach {url}: {e}") from e

    if not resp.ok:
        raise OnboardingAPIError(f"Login failed (HTTP {resp.status_code}): {resp.text[:500]}")

    token = resp.text.strip()
    # Some deployments wrap the token in JSON instead of returning it bare.
    if token.startswith("{"):
        try:
            data = resp.json()
            token = data.get("token") or data.get("access_token") or data.get("jwt") or ""
        except ValueError:
            token = ""

    if not token or token.count(".") != 2:
        raise OnboardingAPIError(f"Login succeeded but no JWT found in the response: {resp.text[:300]}")
    return token


def push_employee_census(jwt_token: str,
                          census_bytes: bytes, census_filename: str,
                          job_title_mapping_bytes: bytes, job_title_mapping_filename: str,
                          license_ec_bytes: bytes = None, license_ec_filename: str = None,
                          prod_host: str = DEFAULT_PROD_HOST, timeout: int = 120):
    """POST {prod_host}/app/onboarding/api/employee/census (multipart).

    job_title_mapping_file is REQUIRED by this endpoint (confirmed against the
    reference "Prod-Amazon Onboarding Automation" Postman collection).
    license_and_emergency_contact_file is optional there (disabled in the saved
    example) and stays optional here.

    Returns the raw requests.Response so the caller can inspect status/body.
    """
    url = f"{prod_host.rstrip('/')}/app/onboarding/api/employee/census"
    headers = {"Accept": "application/json", "AuthorizationHeader": jwt_token}
    files = {
        "employee_census_adv_file": (census_filename, census_bytes),
        "job_title_mapping_file": (job_title_mapping_filename, job_title_mapping_bytes),
    }
    if license_ec_bytes is not None:
        files["license_and_emergency_contact_file"] = (license_ec_filename, license_ec_bytes)
    try:
        return requests.post(url, headers=headers, files=files, timeout=timeout)
    except requests.RequestException as e:
        raise OnboardingAPIError(f"Could not reach {url}: {e}") from e


def automation_id(resp) -> int | None:
    """The run id (onboarding_automation_history.id) from a push response, if any."""
    try:
        rid = (resp.json().get("data") or {}).get("OnboardingAutomationId")
        return int(rid) if rid is not None else None
    except (ValueError, AttributeError, TypeError):
        return None


def fetch_run_log(jwt_token: str, run_id: int, prod_host: str = DEFAULT_PROD_HOST,
                  timeout: int = 60, wait_seconds: int = 15) -> dict:
    """One run's row from onboarding_automation_history, via /app/onboarding/query.

    The API writes error_messages / optional_validations together with end_time as
    its last step before answering the push, so they are normally there already;
    the short wait only covers a row read back before that write is visible.
    Returns the row even if end_time is still empty -- the caller says so.
    """
    url = f"{prod_host.rstrip('/')}/app/onboarding/query"
    body = {"sql": RUN_LOG_SQL.format(run_id=int(run_id)), "page": 0, "size": 1}
    headers = {"Accept": "application/json", "AuthorizationHeader": jwt_token}
    deadline = time.time() + wait_seconds
    while True:
        try:
            resp = requests.post(url, json=body, headers=headers, timeout=timeout)
        except requests.RequestException as e:
            raise OnboardingAPIError(f"Could not reach {url}: {e}") from e
        if not resp.ok:
            raise OnboardingAPIError(f"Run log lookup failed (HTTP {resp.status_code}): {resp.text[:300]}")
        try:
            rows = resp.json().get("data") or []
        except (ValueError, AttributeError):
            raise OnboardingAPIError(f"Run log lookup returned something that isn't JSON: {resp.text[:300]}")
        if not rows:
            raise OnboardingAPIError(f"No run with id {run_id} in the onboarding log.")
        if rows[0].get("end_time") or time.time() >= deadline:
            return rows[0]
        time.sleep(3)


def run_issues(blob) -> list[dict]:
    """error_messages / optional_validations -> one dict per employee row.

    The column holds JSON text {"<Module>": [{rowNumber, employeeId, errorType,
    errorDetails}, ...]}. When the API could not serialise its failures it holds a
    plain sentence instead, which is kept as a single row rather than dropped.
    """
    if not blob:
        return []
    obj = blob
    if isinstance(blob, str):
        try:
            obj = json.loads(blob)
        except ValueError:
            return [{"Module": "-", "Row": None, "Employee ID": None, "Type": None, "Reason": blob.strip()}]
    out = []
    if isinstance(obj, dict):
        for module, items in obj.items():
            for it in items or []:
                if isinstance(it, dict):
                    out.append({"Module": module, "Row": it.get("rowNumber"),
                                "Employee ID": it.get("employeeId"), "Type": it.get("errorType"),
                                "Reason": (it.get("errorDetails") or "").strip()})
                else:
                    out.append({"Module": module, "Row": None, "Employee ID": None,
                                "Type": None, "Reason": str(it)})
    return out


def _render_issue_groups(issues, label):
    """One line per distinct reason, with its count and the affected Employee IDs."""
    groups = {}
    for i in issues:
        groups.setdefault((i["Module"], i["Reason"]), []).append(str(i["Employee ID"] or "-"))
    rows = []
    for (module, reason), ids in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        shown = ", ".join(ids[:5]) + (f" (+{len(ids) - 5} more)" if len(ids) > 5 else "")
        rows.append({"Employees": len(ids), "Module": module, "Reason": reason, "Employee IDs": shown})
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    if len(issues) > len(rows):
        with st.expander(f"View all {len(issues)} {label} rows"):
            st.dataframe(pd.DataFrame(issues), hide_index=True, use_container_width=True)


def render_push_result(result: dict, key_prefix: str):
    """The push outcome plus what the API logged for that run (errors / warnings)."""
    if result["ok"]:
        st.success(f"✅ Census pushed successfully (HTTP {result['status']}).")
    else:
        st.error(f"❌ API returned HTTP {result['status']}")
    if result.get("text"):
        with st.expander("Response details", expanded=not result["ok"]):
            st.code(result["text"])

    run_id = result.get("run_id")
    if run_id is None:
        return
    st.markdown(f"#### 📋 What the API logged for run {run_id}")
    if result.get("run_error"):
        st.warning(f"Couldn't read the log for this run: {result['run_error']}\n\n"
                   f"The push itself is finished — its errors are stored under run **{run_id}**.")
        return
    row = result.get("run") or {}
    if not row.get("end_time"):
        st.info("Uzio is still processing this run, so its errors aren't written yet. "
                "Click **Check the run log again** in a moment.")
        return

    errors = run_issues(row.get("error_messages"))
    warnings = run_issues(row.get("optional_validations"))
    if not errors and not warnings:
        st.success("No errors or warnings were logged for this run.")
        return
    if errors:
        n = len(errors)
        st.markdown(_callout(
            "error", f"❌ {n} record{'s' if n != 1 else ''} failed",
            "The API skipped these — they were not created or updated. Fix them in the source and push again."),
            unsafe_allow_html=True)
        _render_issue_groups(errors, "error")
    if warnings:
        n = len(warnings)
        st.markdown(_callout(
            "warn", f"⚠️ {n} warning{'s' if n != 1 else ''}",
            "These records went through, but the API flagged something on each one — please review.",
            margin="16px 0 4px 0"),
            unsafe_allow_html=True)
        _render_issue_groups(warnings, "warning")

    issues = ([{"Severity": "Error", **e} for e in errors]
              + [{"Severity": "Warning", **w} for w in warnings])
    st.download_button(
        "📥 Download errors and warnings (CSV)",
        pd.DataFrame(issues).to_csv(index=False).encode("utf-8"),
        file_name=f"onboarding_run_{run_id}_issues.csv", mime="text/csv",
        key=f"{key_prefix}_issues_dl",
    )


def render_push_to_uzio_section(vendor: str, data_key: str, jt_key_prefix: str, key_prefix: str):
    """Renders the 'Push Census to Uzio (Production)' section.

    vendor: "ADP" or "PAYCOM" -- sent to the login endpoint.
    data_key: session_state key holding the cleaned census bytes, set by the Census
        Sanity tool's download-button block ({"xlsx":..., "csv":..., "audit":...}).
    jt_key_prefix: the key_prefix passed to job_title_mapper.render_streamlit_section
        for this same file -- used to retrieve the mapping CSV it stashed.
    """
    st.markdown("---")
    st.markdown("### \U0001F680 Push Census to Uzio (Production)")
    st.warning(
        "This sends the corrected census straight to the **live Uzio onboarding API** "
        "and creates/updates real employee records for the employer below. "
        "Double-check the FEIN and the files before submitting."
    )

    cached = st.session_state.get(data_key, {})
    census_bytes = cached.get("csv")
    if not census_bytes:
        st.info("Run the sanity check above first — the corrected census isn't ready yet.")
        return

    jt_mapping = st.session_state.get(f"{jt_key_prefix}_job_title_mapping")
    if not jt_mapping:
        st.info("Complete the **Amazon Job Title Mapping** table above first — this API requires it.")
        return

    fein = st.text_input(
        "Employer FEIN", key=f"{key_prefix}_fein",
        help="Same FEIN used to log into Uzio for this employer.",
    )
    col_u, col_p = st.columns(2)
    with col_u:
        username = st.text_input("Uzio Username", key=f"{key_prefix}_user")
    with col_p:
        password = st.text_input(
            "Uzio Password", type="password", key=f"{key_prefix}_pass",
            help="Never stored -- used only for this request.",
        )

    include_lic = st.checkbox(
        "Also include a License & Emergency Contact file (optional)",
        key=f"{key_prefix}_inc_lic",
    )
    lic_file = None
    if include_lic:
        lic_file = st.file_uploader(
            "License & Emergency Contact file", type=["csv", "xlsx"],
            key=f"{key_prefix}_lic_upload",
        )

    confirm = st.checkbox(
        f"I confirm this pushes to **PRODUCTION** for FEIN `{fein or '____'}` and I've reviewed the files.",
        key=f"{key_prefix}_confirm",
    )

    result_key = f"{key_prefix}_last_push"
    if st.button("\U0001F680 Push to Uzio", key=f"{key_prefix}_btn", disabled=not confirm):
        if not (fein.strip() and username.strip() and password):
            st.error("FEIN, Username, and Password are all required.")
            return
        try:
            with st.spinner("Logging in to Uzio..."):
                token = login(username.strip(), password, fein.strip(), vendor)
            with st.spinner("Uploading census..."):
                lic_bytes = lic_file.getvalue() if lic_file else None
                lic_name = lic_file.name if lic_file else None
                resp = push_employee_census(
                    token,
                    census_bytes, f"{vendor}_Census.csv",
                    jt_mapping["csv"], jt_mapping["filename"],
                    lic_bytes, lic_name,
                )
        except OnboardingAPIError as e:
            st.session_state.pop(result_key, None)
            st.error(f"❌ {e}")
            return
        result = {"ok": resp.ok, "status": resp.status_code, "text": resp.text[:3000],
                  "run_id": automation_id(resp), "run": None, "run_error": None}
        if result["run_id"] is not None:
            with st.spinner(f"Reading the API's log for run {result['run_id']}..."):
                try:
                    result["run"] = fetch_run_log(token, result["run_id"])
                except OnboardingAPIError as e:
                    result["run_error"] = str(e)
        st.session_state[result_key] = result

    result = st.session_state.get(result_key)
    if not result:
        return
    render_push_result(result, key_prefix)

    unfinished = result.get("run_id") is not None and (
        result.get("run_error") or not (result.get("run") or {}).get("end_time"))
    if unfinished and st.button("🔄 Check the run log again", key=f"{key_prefix}_recheck"):
        try:
            token = login(username.strip(), password, fein.strip(), vendor)
            result["run"] = fetch_run_log(token, result["run_id"])
            result["run_error"] = None
        except OnboardingAPIError as e:
            result["run_error"] = str(e)
        st.session_state[result_key] = result
        st.rerun()
