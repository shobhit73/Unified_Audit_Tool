"""Test the real MCP handler for paycom_prior_payroll_setup_helper."""
import sys, asyncio, os, json
sys.path.insert(0, r"c:\Users\shobhit.sharma\Downloads\Deduction Tool\audit_fast_api")
import mcp_server


async def main():
    args = {
        "prior_payroll_path": r"C:\Users\shobhit.sharma\Downloads\Accelerated Logistics Pior Payroll Setup\Accelerated Paycom Prior Payroll 04122026_04252026_05012026.csv",
        "scheduled_deductions_path": r"C:\Users\shobhit.sharma\Downloads\Accelerated Logistics Pior Payroll Setup\Paycom Accelerated Logistics Scheduled Deductions 27th April.xlsx",
    }
    res = await mcp_server.handle_call_tool("paycom_prior_payroll_setup_helper", args)
    print("Handler response:")
    print(res[0].text[:2000])

    # Negative test - pass an ADP file as prior_payroll, expect refusal
    print("\n\n--- Negative test: ADP file in prior_payroll slot ---")
    bad = {
        "prior_payroll_path": r"C:\Users\shobhit.sharma\Downloads\Carvan Prior Payroll Setup\Payroll_History_Q1_Consolidated.csv",
        "scheduled_deductions_path": r"C:\Users\shobhit.sharma\Downloads\Accelerated Logistics Pior Payroll Setup\Paycom Accelerated Logistics Scheduled Deductions 27th April.xlsx",
    }
    res = await mcp_server.handle_call_tool("paycom_prior_payroll_setup_helper", bad)
    print(res[0].text[:600])

    # Confirm the deleted tool is gone
    print("\n\n--- Negative test: deleted tool name ---")
    res = await mcp_server.handle_call_tool("paycom_deduction_analyzer", {})
    print(res[0].text[:400])


asyncio.run(main())
