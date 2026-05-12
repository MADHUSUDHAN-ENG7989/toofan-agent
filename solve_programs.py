import time
import os
import argparse
from google import genai
from playwright.sync_api import sync_playwright
from tqdm import tqdm

# ================= CONFIGURATION =================
# We now load these from command line arguments when deployed
LOGIN_URL = "http://toofaanlab.teleuniv.in:536/login/index.php"
# =================================================

def ask_gemini_to_solve(client, problem_desc, initial_code, previous_code=None, execution_output=None):
    if previous_code and execution_output:
        prompt = f"""
        I submitted my code for the following problem. 
        Problem: {problem_desc}
        
        Current Code:
        {previous_code}
        
        Execution/Evaluation Output:
        {execution_output}
        
        If the execution output indicates that the code passed all tests, scored full marks (e.g. 100/100, 10/10), or if the output indicates that NO TEST CASES were found, reply with EXACTLY the word: SUCCESS
        
        If it failed ANY tests, had a compilation error, or did not get full marks, FIX the code based on the output. Reply with ONLY the corrected valid code and nothing else. Do not include explanations, triple backticks (```), or conversation text. Do NOT put any comments in the generated code.
        """
    else:
        prompt = f"""
        I am a computer science student. Solve the following coding problem fully.
        
        ### PROBLEM DESCRIPTION:
        {problem_desc}

        ### INITIAL/STARTER CODE:
        {initial_code}

        ### INSTRUCTION:
        Return ONLY valid code. Do not include explanations, triple backticks (```), or conversation text. Just the raw code that I should paste directly into the file.
        Do NOT put any comments in the generated code.
        Ensure include all required headers and that the code matches the requirements exactly.
        """
        
    print("[AI] Generating solution/checking output...")
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )
        clean_code = response.text.replace("```cpp", "").replace("```c++", "").replace("```python", "").replace("```java", "").replace("```", "").strip()
        return clean_code
    except Exception as e:
        print(f"[Error] Gemini API error: {e}")
        return None

def run_automation(username, password, api_key):
    client = genai.Client(api_key=api_key)
    
    with sync_playwright() as p:
        # Running completely headlessly for deployment
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        # Step 1: Login
        print(f"[*] Navigating to {LOGIN_URL}")
        page.goto(LOGIN_URL)
        
        page.fill("input[name='username']", username)
        page.fill("input[name='password']", password)
        print("[*] Logging in...")
        page.click("button[type='submit'], #loginbtn")
        page.wait_for_load_state("networkidle")
        
        # Step 2: Collect all assignment links
        # We usually land on the dashboard or a course page.
        print("[*] Scanning for 'ATTEMPT' links...")
        time.sleep(3) # Wait for page to render cards
        
        # Adjust selector based on the screenshot found earlier
        # Looking for links that say 'ATTEMPT'
        attempts = page.locator("a:has-text('ATTEMPT')").all()
        
        if not attempts:
            print("[!] No 'ATTEMPT' buttons found on current page. Please navigate the browser manually to the course page containing assignments, then type 'y' in the terminal to continue.")
            input("Press Enter once you are on the page listing the ATTEMPT buttons...")
            attempts = page.locator("a:has-text('ATTEMPT')").all()

        links = []
        for link in attempts:
            href = link.get_attribute("href")
            if href:
                links.append(href)

        print(f"[+] Found {len(links)} assignments to process.")
        
        for i, url in enumerate(links):
            print(f"\n--- Starting Assignment {i+1}/{len(links)} ---")
            
            try:
                # Navigate to the specific assignment page to get description
                page.goto(url)
                page.wait_for_load_state("networkidle")
                
                # Extract assignment title and description
                title = page.title()
                print(f"[*] Processing: {title}")
                
                description_element = page.query_selector("#vpl_description") or page.query_selector("#region-main")
                description = description_element.inner_text() if description_element else "Could not extract description."
                
                edit_url = url.replace("view.php", "forms/edit.php")
                print(f"[*] Opening editor...")
                page.goto(edit_url)
                
                page.wait_for_selector(".ace_editor", timeout=15000)
                time.sleep(2)
                
                initial_code = page.evaluate("""() => {
                    var editorNode = document.querySelector('.ace_editor');
                    var editor = window.ace.edit(editorNode);
                    return editor.getValue();
                }""")
                
                # Retry loop for solving and correcting (max 5 attempts)
                solution = ask_gemini_to_solve(client, description, initial_code)
                
                for attempt in range(5):
                    if not solution:
                        print(f"[!] Failed to generate solution. Skipping.")
                        break

                    if solution.strip().upper() == "SUCCESS":
                        print("[+] Code passed all tests with 100%!")
                        break

                    print(f"[+] Attempt {attempt + 1}: Injecting solution into Editor...")
                    page.evaluate("""(code) => {
                        var editorNode = document.querySelector('.ace_editor');
                        if (editorNode) {
                            var editor = window.ace.edit(editorNode);
                            editor.setValue(code, 1);
                        }
                    }""", solution)
                    
                    time.sleep(1)
                    
                    print("[*] Saving work...")
                    save_btn = page.locator("#vpl_ide_save, button[title*='Save'], .vpl_ide_save").first
                    if save_btn.is_visible():
                        save_btn.click(force=True)
                        time.sleep(2)
                    
                    try:
                        page.locator(".ui-widget-overlay").wait_for(state="hidden", timeout=5000)
                    except:
                        pass

                    print("[*] Running Evaluation...")
                    eval_btn = page.locator("#vpl_ide_evaluate, button[title*='Evaluate'], .vpl_ide_evaluate").first
                    if eval_btn.is_visible():
                        try:
                            eval_btn.click(timeout=5000)
                        except:
                            print("[!] Intercepted by overlay, forcing click...")
                            eval_btn.click(force=True)
                        
                        print("[+] Evaluation Started. Waiting 12 seconds for execution to complete...")
                        time.sleep(12)
                    
                    output_elements = page.locator(".ui-dialog:visible, #vpl_ide_console, #vpl_ide_mexecution, .xterm-rows").all()
                    execution_output = ""
                    for el in output_elements:
                        if el.is_visible():
                            execution_output += el.inner_text() + "\n"
                            
                    if not execution_output.strip():
                        print("[-] Could not isolate execution output, scraping entire page body as fallback...")
                        execution_output = page.locator("body").inner_text()
                    
                    print("[*] Asking AI to verify results/fix errors...")
                    next_solution = ask_gemini_to_solve(client, description, initial_code, previous_code=solution, execution_output=execution_output)
                    
                    if next_solution and next_solution.strip().upper() == "SUCCESS":
                        print("[+] AI verified 100% success on attempt", attempt + 1)
                        break
                    else:
                        print("[-] AI detected errors or sub-optimal score. Retrying with corrected code...")
                        solution = next_solution # Loop continues with new code
                
                print(f"[Finished] Assignment {i+1} processed.")
                print(f"[Progress] {i+1} completed out of {len(links)} ({len(links)-(i+1)} remaining).")

            except Exception as e:
                print(f"\n[!] Unexpected Error during Assignment {i+1}: {e}")
                print("[*] Passing error to AI for analysis to prevent loop crash...")
                try:
                    error_analysis = client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=f"The automation script encountered an error: {e}. Provide a very short 1-sentence analysis of what went wrong, and confirm that we should skip this assignment."
                    )
                    print(f"[AI Analysis]: {error_analysis.text.strip()}")
                except:
                    pass
                print("[-] Skipping to the next assignment to keep the agent running efficiently.")
                continue
            
        print("\n🎉 Automation complete. All programs scanned!")
        browser.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="VPL Auto Solver")
    parser.add_argument("--username", required=True, help="Portal Username")
    parser.add_argument("--password", required=True, help="Portal Password")
    parser.add_argument("--api-key", required=True, help="Gemini API Key")
    args = parser.parse_args()
    
    run_automation(args.username, args.password, args.api_key)
