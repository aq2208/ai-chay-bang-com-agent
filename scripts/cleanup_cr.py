#!/usr/bin/env python3
import json
import subprocess
import sys

def run_bash_cmd(cmd):
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {cmd}\nExit code: {e.returncode}\nStderr: {e.stderr}", file=sys.stderr)
        return None

def get_protected_tags():
    protected_tags = set()
    print("Fetching runtimes to identify protected tags...")
    runtimes_json = run_bash_cmd("bash scripts/runtime.sh list")
    if not runtimes_json:
        return protected_tags
    
    try:
        runtimes_data = json.loads(runtimes_json)
        runtimes = runtimes_data.get("listData", [])
    except Exception as e:
        print(f"Error parsing runtimes JSON: {e}", file=sys.stderr)
        return protected_tags

    for rt in runtimes:
        rt_id = rt.get("id")
        rt_name = rt.get("name")
        if not rt_id:
            continue
        
        # Get endpoints to see active version numbers
        endpoints_json = run_bash_cmd(f"bash scripts/runtime.sh endpoints list {rt_id}")
        if not endpoints_json:
            continue
        try:
            endpoints_data = json.loads(endpoints_json)
            active_versions = {ep.get("version") for ep in endpoints_data.get("listData", []) if ep.get("version") is not None}
        except Exception as e:
            print(f"Error parsing endpoints for {rt_name}: {e}", file=sys.stderr)
            active_versions = set()

        if not active_versions:
            continue

        # Get versions to translate version numbers to imageUrls
        versions_json = run_bash_cmd(f"bash scripts/runtime.sh versions {rt_id} --page 1 --size 20")
        if not versions_json:
            continue
        try:
            versions_data = json.loads(versions_json)
            for ver in versions_data.get("listData", []):
                ver_num = ver.get("version")
                if ver_num in active_versions:
                    img_url = ver.get("imageUrl")
                    if img_url:
                        # Extract tag from image:tag format
                        # E.g., vcr.vngcloud.vn/111480-abp111948/ai-chay-bang-com-agent:v3 -> v3
                        parts = img_url.split(":")
                        if len(parts) > 1:
                            tag = parts[-1]
                            protected_tags.add(tag)
                            print(f"Protected tag identified: {tag} (active on {rt_name} version {ver_num})")
        except Exception as e:
            print(f"Error parsing versions for {rt_name}: {e}", file=sys.stderr)

    return protected_tags

def check_and_cleanup(force=False):
    # Check quota
    repo_json = run_bash_cmd("bash scripts/cr.sh repo get")
    if not repo_json:
        print("Failed to get registry repository info. Skipping cleanup.")
        return
    
    try:
        repo_data = json.loads(repo_json)
        quota_used = repo_data.get("quotaUsed", 0)
        quota_limit = repo_data.get("quotaLimit", 0)
    except Exception as e:
        print(f"Error parsing repository info JSON: {e}", file=sys.stderr)
        return

    gb = 1024 * 1024 * 1024
    print(f"Registry Quota: {quota_used / gb:.2f} GB / {quota_limit / gb:.2f} GB used.")

    # 3 GB margin before we trigger cleanup
    trigger_threshold = 3.0 * gb
    if force:
        print("Force flag set. Triggering cleanup...")
    elif quota_limit - quota_used < trigger_threshold:
        print(f"Remaining space is less than 3 GB. Triggering cleanup...")
    else:
        print("Remaining space is sufficient. Cleanup not required.")
        return

    protected_tags = get_protected_tags()

    # List images
    images_json = run_bash_cmd("bash scripts/cr.sh images list")
    if not images_json:
        print("Failed to list registry images.")
        return
    try:
        images_data = json.loads(images_json)
        images = images_data.get("data", [])
    except Exception as e:
        print(f"Error parsing images list: {e}", file=sys.stderr)
        return

    for img in images:
        img_name = img.get("name")
        if not img_name:
            continue
        
        print(f"Processing image repository: {img_name}")
        artifacts_json = run_bash_cmd(f"bash scripts/cr.sh artifacts list --image {img_name}")
        if not artifacts_json:
            continue
        
        try:
            artifacts_data = json.loads(artifacts_json)
            artifacts = artifacts_data.get("data", [])
        except Exception as e:
            print(f"Error parsing artifacts list for {img_name}: {e}", file=sys.stderr)
            continue

        # Sort artifacts by pushTime descending (newest first)
        artifacts.sort(key=lambda x: x.get("pushTime", ""), reverse=True)

        for i, art in enumerate(artifacts):
            digest = art.get("digest")
            tags = [t.get("name") for t in art.get("tags", []) if t.get("name")]
            
            # Check if this artifact is protected:
            # - Top 2 newest artifacts (index 0 and 1) are kept for rollback/redundancy
            # - If any of the tags are in protected_tags
            is_newest = (i < 2)
            is_active = any(tag in protected_tags for tag in tags)

            if is_newest or is_active:
                reason = "newest" if is_newest else "active runtime version"
                print(f"  Keeping artifact {digest[:12]} (Tags: {tags}) - Reason: {reason}")
            else:
                print(f"  Deleting unused artifact {digest[:12]} (Tags: {tags})...")
                run_bash_cmd(f"bash scripts/cr.sh artifacts delete --image {img_name} --digest {digest}")

if __name__ == "__main__":
    force_cleanup = "--force" in sys.argv
    check_and_cleanup(force=force_cleanup)
