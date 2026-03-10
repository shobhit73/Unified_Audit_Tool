---
description: Login to ADP Workforce Now and download the Employee Census report with human assistance for MFA.
---

### Prerequisites
- Target employer credentials (User ID and Password).
- Access to the MFA device/email if required.

### Key Learnings for Speed
- **Skip "Edit/Run"** — use `Options → Run` directly. This avoids loading the heavy report editor.
- **Skip "View Report" page** — after clicking Run, navigate straight to the Output tab. The "View Report" page renders all employee records and causes browser timeouts.
- **Runtime Settings auto-accepts** — "Data as of: Most Recent" is always pre-filled. Just click Run immediately without inspecting it.
- **Export opens a new tab automatically** — no need to click "Done". When the export tab shows "Report processing completed successfully", the file is already saved.
- **Use direct URLs** to skip navigation steps and avoid menu loading delays.

---

### Workflow Steps

1. **Navigate to ADP Sign-In**
   - Open: `https://online.adp.com/signin/v1/?APPID=WFNPortal&productId=80e309c3-7085-bae1-e053-3505430b5495&returnURL=https://workforcenow.adp.com/&callingAppId=WFN`

2. **Enter User ID**
   - Find the "User ID" textbox, enter the provided User ID, and click **Next**.

3. **MFA / Security Question Check (Human-in-the-Loop)**
   - Check if the page shows a security question, "Verify your identity" prompt, or MFA code field.
   - **If MFA/Question is detected**:
     - Take a screenshot of the prompt.
     - Call `notify_user` with the screenshot and ask: "ADP requires verification. Please provide the answer or code."
     - Wait for user response before proceeding.

4. **Enter Password**
   - Once the password field appears, enter the provided Password and click **Sign In**.

5. **Navigate Directly to All Custom Reports**
   // turbo
   - Navigate directly to:
     `https://workforcenow.adp.com/theme/admin.html#/Reports/ReportsTabCustomReportsCategoryAllReports`
   - This skips manually clicking through the Reports & Analytics menu.

6. **Trigger Report Run (Fast Path)**
   - Locate the **"Employee Census Report"** row in the grid.
   - Click the **Options (⋯)** button at the right of the row.
   - Click **"Run"** (NOT "Edit/Run" — this skips the slow report editor page).
   - A **"Runtime Settings"** modal appears — "Data as of: Most Recent" is already set. Click **Run** immediately.

7. **Wait for Export Tab and Verify Completion**
   - ADP opens a new tab titled "ADP Reporting - CSV report".
   - Switch to that tab and wait for: **"Report processing completed successfully."**
   - The file `Employee-Census-Report.csv` is now saved automatically.
   - **Do NOT wait for or try to click "Done"** — the button is hidden and the file is already downloaded.

8. **Notify User of Completion**
   - Navigate back to the Reports tab.
   - Confirm the file is present in the `.playwright-mcp` directory.
   - Notify the user that the Employee Census Report has been downloaded successfully.
