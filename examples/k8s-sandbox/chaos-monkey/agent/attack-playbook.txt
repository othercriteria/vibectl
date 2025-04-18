# Kubernetes Chaos Monkey Attack Playbook

This playbook outlines strategies for introducing controlled chaos into a Kubernetes cluster to test system resilience.

## Core Attack Vectors

### 1. Pod Disruption

**Strategy**: Delete pods to test auto-recovery and resilience
- `kubectl delete pod <pod-name> -n services`
- Target stateful components first (database, cache)
- Delete multiple pods simultaneously to increase stress
- Delete pods in specific patterns (all from one node, all of one type)

**Expected Impact**:
- Temporary service disruption
- Increased latency during recovery
- Potential data loss if persistence not configured properly

### 2. Deployment Manipulation

**Strategy**: Scale deployments up/down to test elasticity and resource management
- `kubectl scale deployment <deployment-name> -n services --replicas=0`
- Scale critical services to zero replicas
- Rapidly scale up/down to create resource contention
- Target frontend and backend services to affect user experience

**Expected Impact**:
- Service unavailability if scaled to zero
- Potential resource exhaustion if scaled too high
- Degraded performance during scaling events

### 3. Resource Constraints

**Strategy**: Manipulate resource limits/requests to create bottlenecks
- Edit deployment to add strict CPU/memory limits
- Create resource quota constraints at namespace level
- Introduce competing workloads that consume significant resources

**Expected Impact**:
- Container throttling
- OOMKill events
- Degraded performance or crashed pods

### 4. Configuration Sabotage

**Strategy**: Modify ConfigMaps and Secrets to inject misconfigurations
- Change database connection strings
- Modify application settings to invalid values
- Update environment variables to break functionality

**Expected Impact**:
- Application errors
- Failed connections
- Degraded functionality with potentially subtle effects

### 5. Network Disruption

**Strategy**: Implement network policies that block essential communication
- Create restrictive NetworkPolicy objects
- Modify Service definitions to point to wrong targets
- Change ports or targeting labels

**Expected Impact**:
- Failed inter-service communication
- Timeout errors
- Degraded user experience

### 6. State Corruption

**Strategy**: Modify persistent state to test data integrity measures
- If using PersistentVolumes, corrupt data if accessible
- Modify database entries to invalid states
- Fill storage to capacity

**Expected Impact**:
- Application errors
- Data consistency issues
- Potential service outages

## Advanced Techniques

### Cascading Failures

**Strategy**: Target dependencies to create cascading effects
1. Identify critical service dependencies
2. Disrupt the most fundamental dependency first
3. Observe how failure propagates through the system

### Intermittent Disruption

**Strategy**: Create unpredictable, sporadic failures that are harder to diagnose
- Introduce random delays into network connections
- Temporarily block access to services
- Restart pods on a random schedule

### Restore Impediment

**Strategy**: Interfere with recovery mechanisms
- Delete ConfigMaps right after they're recreated
- Scale deployments down immediately after they scale up
- Create resource pressure that prevents rescheduling

## Documentation Template

For each attack, document:

```
## Attack: [Name]
- Timestamp: [When executed]
- Target: [Resource affected]
- Method: [Commands/actions taken]
- Expected Impact: [What should happen]
- Observed Results: [What actually happened]
- Recovery Time: [How long until blue team recovered]
- Insights: [Lessons learned]
```

Remember to vary attack types and timing to prevent the blue team from developing a fixed response pattern.
