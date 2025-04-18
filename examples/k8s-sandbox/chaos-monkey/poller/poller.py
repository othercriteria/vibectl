#!/usr/bin/env python3
"""
Chaos Monkey Service Poller

Monitors the health of the frontend service in the Kubernetes cluster.
The overseer will be responsible for tracking historical state.
"""

import os
import sys
import time
import subprocess
import json
import logging
from typing import Optional, Dict, Any, Union

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("poller")

# ANSI color codes for terminal output
class Colors:
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    RED = '\033[0;31m'
    BLUE = '\033[0;34m'
    NC = '\033[0m'  # No Color

# Configuration from environment variables
POLL_INTERVAL_SECONDS = int(os.environ.get('POLL_INTERVAL_SECONDS', 15))
DELAY_SECONDS = int(os.environ.get('DELAY_SECONDS', 15))
SESSION_DURATION = int(os.environ.get('SESSION_DURATION', 30))
KUBECONFIG = os.environ.get('KUBECONFIG', '/config/kube/config')
STATUS_DIR = os.environ.get('STATUS_DIR', '/tmp/status')
STATUS_FILE = f"{STATUS_DIR}/service_status.json"
KIND_CONTAINER = os.environ.get('KIND_CONTAINER', 'chaos-monkey-control-plane')

# Status constants
STATUS_DOWN = 0       # Service is unreachable
STATUS_DEGRADED = 1   # Service is reachable but has issues
STATUS_HEALTHY = 2    # Service is fully operational

def run_command(cmd: Union[str, list], shell: bool = False) -> Optional[str]:
    """Run a command and return its output."""
    try:
        if shell:
            result = subprocess.run(cmd, shell=True, text=True, capture_output=True, timeout=30)
        else:
            result = subprocess.run(cmd, text=True, capture_output=True, timeout=30)
        
        if result.returncode != 0:
            logger.debug(f"Command failed with code {result.returncode}: {cmd}")
            logger.debug(f"Error: {result.stderr}")
            return None
        
        return result.stdout.strip() if result.stdout else None
    
    except subprocess.TimeoutExpired:
        logger.warning(f"Command timed out: {cmd}")
        return None
    except Exception as e:
        logger.error(f"Error running command: {e}")
        return None

def wait_for_kubeconfig() -> None:
    """Wait for the kubeconfig file to become available."""
    if not os.path.exists(KUBECONFIG):
        logger.warning(f"{Colors.YELLOW}Kubeconfig not found at {KUBECONFIG}. Waiting...{Colors.NC}")
        
        for i in range(30):
            if os.path.exists(KUBECONFIG):
                logger.info(f"{Colors.GREEN}Kubeconfig found after waiting!{Colors.NC}")
                break
            sys.stdout.write(".")
            sys.stdout.flush()
            time.sleep(5)
            if i == 29:
                logger.error(f"{Colors.RED}Kubeconfig still not available after waiting. Exiting.{Colors.NC}")
                sys.exit(1)
    
    logger.info(f"{Colors.GREEN}Using kubeconfig at {KUBECONFIG}{Colors.NC}")

def find_sandbox_container() -> Optional[str]:
    """Find the container ID or name of the k8s-sandbox container."""
    # First try searching based on the KIND_CONTAINER value
    if KIND_CONTAINER:
        result = run_command(["docker", "ps", "-q", "--filter", f"name={KIND_CONTAINER}"])
        if result:
            return KIND_CONTAINER
    
    # Try getting container ID based on name pattern
    result = run_command(
        ["docker", "ps", "--format", "{{.ID}}",
         "--filter", "name=k8s-sandbox",
         "--filter", "name=chaos-monkey-k8s-sandbox"]
    )
    
    if result:
        return result
    
    # Try getting container name
    result = run_command(
        ["docker", "ps", "--format", "{{.Names}}",
         "--filter", "name=k8s-sandbox",
         "--filter", "name=chaos-monkey-k8s-sandbox"]
    )
    
    return result

def check_kubernetes_status(sandbox_container: str) -> bool:
    """Check if the Kubernetes cluster is running."""
    cmd = f'docker exec {sandbox_container} kubectl get nodes'
    result = run_command(cmd, shell=True)
    
    if result and "Ready" in result:
        logger.info(f"{Colors.GREEN}Kubernetes cluster is running{Colors.NC}")
        return True
    else:
        logger.error(f"{Colors.RED}Kubernetes cluster is not available{Colors.NC}")
        return False

def check_frontend_service(sandbox_container: str) -> Dict[str, Any]:
    """Check the health of the frontend service and return its status."""
    service_info = {
        "status": STATUS_DOWN,
        "response_time": "N/A",
        "message": "Service unavailable",
        "endpoint": "unknown"
    }
    
    # First, check if the frontend service exists
    cmd = f'docker exec {sandbox_container} kubectl get service frontend -n services -o json'
    result = run_command(cmd, shell=True)
    
    if not result:
        logger.warning(f"{Colors.YELLOW}Frontend service not found{Colors.NC}")
        service_info["message"] = "Service not found"
        return service_info
    
    try:
        # Parse service information
        service_data = json.loads(result)
        
        # Get the ClusterIP
        cluster_ip = service_data.get("spec", {}).get("clusterIP")
        if not cluster_ip or cluster_ip == "None":
            logger.warning(f"{Colors.YELLOW}No ClusterIP for frontend service{Colors.NC}")
            service_info["message"] = "No ClusterIP assigned"
            return service_info
        
        # Get the port
        port = service_data.get("spec", {}).get("ports", [{}])[0].get("port")
        if not port:
            logger.warning(f"{Colors.YELLOW}No port found for frontend service{Colors.NC}")
            service_info["message"] = "No port assigned"
            return service_info
        
        # Save endpoint information
        service_info["endpoint"] = f"http://{cluster_ip}:{port}"
        
        # Start timing the request
        start_time = time.time()
        
        # Check if the service responds
        cmd = f'docker exec {sandbox_container} curl -s --connect-timeout 2 --max-time 5 -o /dev/null -w "%{{http_code}}" "{service_info["endpoint"]}" 2>/dev/null || echo "000"'
        response = run_command(cmd, shell=True)
        
        # Calculate response time
        response_time = time.time() - start_time
        service_info["response_time"] = f"{response_time:.2f}s"
        
        # Update service status based on HTTP code
        if response == "200":
            # Check content to verify it's the expected frontend
            cmd = f'docker exec {sandbox_container} curl -s --connect-timeout 2 --max-time 5 "{service_info["endpoint"]}" 2>/dev/null || echo ""'
            content = run_command(cmd, shell=True) or ""
            
            if "Service Status: Online" in content:
                service_info["status"] = STATUS_HEALTHY
                service_info["message"] = "Service healthy"
                logger.info(f"{Colors.GREEN}Frontend service is healthy ({service_info['response_time']}){Colors.NC}")
            else:
                service_info["status"] = STATUS_DEGRADED
                service_info["message"] = "Response OK but content validation failed"
                logger.warning(f"{Colors.YELLOW}Frontend service is responding but content validation failed{Colors.NC}")
        elif response and response.startswith(("4", "5")):
            service_info["status"] = STATUS_DEGRADED
            service_info["message"] = f"HTTP error {response}"
            logger.warning(f"{Colors.YELLOW}Frontend service returned HTTP {response} ({service_info['response_time']}){Colors.NC}")
        else:
            service_info["message"] = "Connection failed"
            logger.error(f"{Colors.RED}Frontend service is down{Colors.NC}")
        
        # Optional: Check frontend pods
        cmd = f'docker exec {sandbox_container} kubectl get pods -n services -l app=frontend -o json'
        pods_result = run_command(cmd, shell=True)
        
        if pods_result:
            try:
                pods_data = json.loads(pods_result)
                pods = pods_data.get("items", [])
                
                ready_pods = sum(1 for pod in pods if all(
                    container.get("ready", False) 
                    for container in pod.get("status", {}).get("containerStatuses", [])
                ))
                
                total_pods = len(pods)
                
                # Add pod information to the service info
                service_info["pods"] = {
                    "ready": ready_pods,
                    "total": total_pods
                }
                
                # If no pods are ready but the service seems healthy, mark as degraded
                if ready_pods == 0 and total_pods > 0 and service_info["status"] == STATUS_HEALTHY:
                    service_info["status"] = STATUS_DEGRADED
                    service_info["message"] = "Service accessible but no pods are ready"
                
                logger.info(f"{Colors.BLUE}Frontend pods: {ready_pods}/{total_pods} ready{Colors.NC}")
            except Exception as e:
                logger.error(f"Error parsing pod information: {e}")
        
        return service_info
    
    except Exception as e:
        logger.error(f"Error checking frontend service: {e}")
        service_info["message"] = f"Error: {str(e)}"
        return service_info

def update_status_file(status: Dict[str, Any]) -> None:
    """Write current status to the status file."""
    try:
        # Create status directory if it doesn't exist
        os.makedirs(STATUS_DIR, exist_ok=True)
        
        # Prepare the status data
        status_data = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "frontend": status
        }
        
        # Write to status file
        with open(STATUS_FILE, 'w') as f:
            json.dump(status_data, f, indent=2)
        
        logger.debug(f"Updated status file: {STATUS_FILE}")
    except Exception as e:
        logger.warning(f"Could not write to status file {STATUS_FILE}: {e}")

def print_status(status: Dict[str, Any]) -> None:
    """Print a formatted status report."""
    # Determine status color
    if status["status"] == STATUS_HEALTHY:
        status_color = Colors.GREEN
        status_text = "HEALTHY"
    elif status["status"] == STATUS_DEGRADED:
        status_color = Colors.YELLOW
        status_text = "DEGRADED"
    else:
        status_color = Colors.RED
        status_text = "DOWN"
    
    # Print header
    print("\n" + "=" * 80)
    print(f"{Colors.BLUE}FRONTEND SERVICE STATUS{Colors.NC}")
    print("=" * 80)
    
    # Print status
    print(f"Status: {status_color}{status_text}{Colors.NC}")
    print(f"Response Time: {status['response_time']}")
    print(f"Message: {status['message']}")
    print(f"Endpoint: {status['endpoint']}")
    
    # Print pod information if available
    if "pods" in status:
        print(f"Pods: {status['pods']['ready']}/{status['pods']['total']} ready")
    
    print("=" * 80 + "\n")

def main() -> None:
    """Main function to run the poller."""
    try:
        print("🔍 Starting Chaos Monkey Frontend Service Poller")
        print("👀 Monitoring frontend service health")
        
        # Create status directory
        os.makedirs(STATUS_DIR, exist_ok=True)
        
        # Wait for kubeconfig to be available
        wait_for_kubeconfig()
        
        # Wait for initial delay before starting
        logger.info(f"{Colors.YELLOW}Waiting for initial delay of {DELAY_SECONDS} seconds...{Colors.NC}")
        time.sleep(DELAY_SECONDS)
        
        logger.info(f"{Colors.GREEN}Starting to monitor frontend service...{Colors.NC}")
        
        # Calculate end time based on session duration
        end_time = time.time() + (SESSION_DURATION * 60)
        check_count = 0
        
        while True:
            # Check if session duration has elapsed
            current_time = time.time()
            if current_time >= end_time:
                logger.info(f"{Colors.GREEN}Session duration of {SESSION_DURATION} minutes has elapsed.{Colors.NC}")
                logger.info(f"{Colors.GREEN}Final service status:{Colors.NC}")
                sys.exit(0)
            
            # Find the sandbox container
            sandbox_container = find_sandbox_container()
            if not sandbox_container:
                logger.error(f"{Colors.RED}Could not find sandbox container. Retrying in 10 seconds...{Colors.NC}")
                time.sleep(10)
                continue
            
            # Check if Kubernetes cluster is running
            if not check_kubernetes_status(sandbox_container):
                # If cluster is not running, update status as down and continue
                status = {
                    "status": STATUS_DOWN,
                    "response_time": "N/A",
                    "message": "Kubernetes cluster unavailable",
                    "endpoint": "unknown"
                }
                update_status_file(status)
                time.sleep(POLL_INTERVAL_SECONDS)
                continue
            
            # Check frontend service
            status = check_frontend_service(sandbox_container)
            
            # Print status (full every 3 checks to reduce verbosity)
            if check_count == 0 or check_count % 3 == 0:
                print_status(status)
            else:
                logger.info(f"Service check #{check_count} completed. Use 'make poller-logs' to see full details.")
            
            # Update status file
            update_status_file(status)
            
            # Increment check counter
            check_count += 1
            
            # Wait before next check
            time.sleep(POLL_INTERVAL_SECONDS)
    
    except KeyboardInterrupt:
        logger.info("Poller interrupted by user. Exiting gracefully.")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 