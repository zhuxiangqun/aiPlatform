## FILE: main.py
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid
import asyncio
from enum import Enum

app = FastAPI(title="AutoDelivery Agent", version="1.0.0")

# In-memory storage (replace with DB in production)
projects = {}
users = {"alice": {"name": "Alice", "role": "PM"}, "bob": {"name": "Bob", "role": "Architect"},
          "charlie": {"name": "Charlie", "role": "FE_Engineer"}, "dave": {"name": "Dave", "role": "BE_Engineer"},
          "eve": {"name": "Eve", "role": "Test_Manager"}}

class ProjectStatus(str, Enum):
    INIT = "init"
    REQUIREMENT_GATHERING = "requirement_gathering"
    PRD_REVIEW = "prd_review"
    ARCHITECTURE_DESIGN = "architecture_design"
    ARCHITECTURE_REVIEW = "architecture_review"
    CODING = "coding"
    TEST_CASE_GENERATION = "test_case_generation"
    TEST_CASE_REVIEW = "test_case_review"
    TESTING = "testing"
    BUG_FIXING = "bug_fixing"
    COMPLETED = "completed"

class UserStory(BaseModel):
    id: str
    description: str
    acceptance_criteria: List[str]
    priority: str

class PRD(BaseModel):
    title: str
    overview: str
    user_stories: List[UserStory]
    constraints: List[str]

class ArchitectureComponent(BaseModel):
    name: str
    description: str
    technology_stack: List[str]

class Architecture(BaseModel):
    components: List[ArchitectureComponent]
    diagram_url: Optional[str] = None

class TestCase(BaseModel):
    id: str
    description: str
    expected_result: str
    status: str = "pending"

class TestReport(BaseModel):
    test_cases: List[TestCase]
    pass_rate: float
    failed_tests: List[str]
    logs: str

class BugRecord(BaseModel):
    id: str
    description: str
    failed_test_id: str
    fix_date: Optional[datetime] = None
    fix_method: Optional[str] = None
    program_name: Optional[str] = None
    status: str = "open"

class Project(BaseModel):
    id: str
    name: str
    status: ProjectStatus = ProjectStatus.INIT
    team: Dict[str, str] = {}  # role -> user_id
    prd: Optional[PRD] = None
    architecture: Optional[Architecture] = None
    code: Dict[str, str] = {}  # file_path -> code
    test_cases: List[TestCase] = []
    test_reports: List[TestReport] = []
    bugs: List[BugRecord] = []
    audit_log: List[Dict[str, Any]] = []
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

# Request/Response models
class CreateProjectRequest(BaseModel):
    name: str
    requirement_text: str

class TeamConfigRequest(BaseModel):
    project_id: str
    team: Dict[str, str]  # role -> user_id

class PRDReviewRequest(BaseModel):
    project_id: str
    approved: bool
    feedback: Optional[str] = None

class ArchitectureReviewRequest(BaseModel):
    project_id: str
    approved: bool
    feedback: Optional[str] = None

class TestCaseReviewRequest(BaseModel):
    project_id: str
    approved: bool
    feedback: Optional[str] = None

# Agent simulation functions (replace with actual AI calls)
async def simulate_prd_generation(requirement_text: str) -> PRD:
    """Simulate PRD generation from requirement text"""
    await asyncio.sleep(2)  # Simulate AI processing
    return PRD(
        title="Sample Project",
        overview=f"Auto-generated PRD from: {requirement_text[:50]}...",
        user_stories=[
            UserStory(id="US1", description="User can login", acceptance_criteria=["AC1: Login form exists"], priority="P0"),
            UserStory(id="US2", description="User can view dashboard", acceptance_criteria=["AC1: Dashboard shows data"], priority="P1")
        ],
        constraints=["Must use OAuth2"]
    )

async def simulate_architecture_design(prd: PRD) -> Architecture:
    """Simulate architecture design from PRD"""
    await asyncio.sleep(2)
    return Architecture(
        components=[
            ArchitectureComponent(name="Frontend", description="React SPA", technology_stack=["React", "TypeScript"]),
            ArchitectureComponent(name="Backend", description="FastAPI server", technology_stack=["Python", "FastAPI"]),
            ArchitectureComponent(name="Database", description="PostgreSQL", technology_stack=["PostgreSQL"])
        ]
    )

async def simulate_coding(architecture: Architecture) -> Dict[str, str]:
    """Simulate code generation"""
    await asyncio.sleep(3)
    return {
        "main.py": "print('Hello World')",
        "app/models.py": "class User: pass",
        "app/routes.py": "from fastapi import APIRouter"
    }

async def simulate_test_case_generation(prd: PRD) -> List[TestCase]:
    """Simulate test case generation from PRD"""
    await asyncio.sleep(2)
    test_cases = []
    for us in prd.user_stories:
        for i, ac in enumerate(us.acceptance_criteria):
            test_cases.append(TestCase(
                id=f"TC_{us.id}_{i}",
                description=f"Test: {ac}",
                expected_result="Pass"
            ))
    return test_cases

async def simulate_testing(code: Dict[str, str], test_cases: List[TestCase]) -> TestReport:
    """Simulate test execution"""
    await asyncio.sleep(2)
    failed = []
    logs = ""
    for tc in test_cases:
        # Simulate some failures
        if "login" in tc.description.lower():
            failed.append(tc.id)
            tc.status = "failed"
            logs += f"{tc.id}: FAILED - Login module not implemented\n"
        else:
            tc.status = "passed"
            logs += f"{tc.id}: PASSED\n"
    pass_rate = (len(test_cases) - len(failed)) / len(test_cases) * 100 if test_cases else 100
    return TestReport(
        test_cases=test_cases,
        pass_rate=pass_rate,
        failed_tests=failed,
        logs=logs
    )

async def simulate_bug_fixing(bug: BugRecord, code: Dict[str, str]) -> Dict[str, str]:
    """Simulate bug fixing"""
    await asyncio.sleep(2)
    # Simulate fix
    bug.fix_date = datetime.now()
    bug.fix_method = "Added login module"
    bug.program_name = "main.py"
    bug.status = "fixed"
    code["main.py"] = code.get("main.py", "") + "\n# Fixed login bug"
    return code

# API Endpoints
@app.post("/projects", response_model=Project)
async def create_project(req: CreateProjectRequest, background_tasks: BackgroundTasks):
    """Step 1: Create project and start requirement gathering"""
    project = Project(
        id=str(uuid.uuid4()),
        name=req.name,
        status=ProjectStatus.REQUIREMENT_GATHERING
    )
    project.audit_log.append({
        "timestamp": datetime.now().isoformat(),
        "action": "project_created",
        "details": f"Requirement: {req.requirement_text[:100]}..."
    })
    
    # Trigger PRD generation in background
    async def generate_prd():
        prd = await simulate_prd_generation(req.requirement_text)
        project.prd = prd
        project.status = ProjectStatus.PRD_REVIEW
        project.audit_log.append({
            "timestamp": datetime.now().isoformat(),
            "action": "prd_generated",
            "details": f"PRD with {len(prd.user_stories)} user stories"
        })
    
    background_tasks.add_task(generate_prd)
    projects[project.id] = project
    return project

@app.post("/projects/{project_id}/team")
async def configure_team(project_id: str, req: TeamConfigRequest):
    """Step 2: Configure team"""
    if project_id not in projects:
        raise HTTPException(status_code=404, detail="Project not found")
    project = projects[project_id]
    
    # Validate users exist
    for role, user_id in req.team.items():
        if user_id not in users:
            raise HTTPException(status_code=400, detail=f"User {user_id} not found")
    
    project.team = req.team
    project.audit_log.append({
        "timestamp": datetime.now().isoformat(),
        "action": "team_configured",
        "details": f"Team: {req.team}"
    })
    return {"message": "Team configured", "team": req.team}

@app.post("/projects/{project_id}/prd-review")
async def review_prd(project_id: str, req: PRDReviewRequest):
    """Step 3: Review PRD"""
    if project_id not in projects:
        raise HTTPException(status_code=404, detail="Project not found")
    project = projects[project_id]
    
    if req.approved:
        project.status = ProjectStatus.ARCHITECTURE_DESIGN
        # Trigger architecture design
        async def design_architecture():
            arch = await simulate_architecture_design(project.prd)
            project.architecture = arch
            project.status = ProjectStatus.ARCHITECTURE_REVIEW
            project.audit_log.append({
                "timestamp": datetime.now().isoformat(),
                "action": "architecture_designed",
                "details": f"Architecture with {len(arch.components)} components"
            })
        
        background_tasks = req.approved  # Hack to get background tasks
        # Actually we need to use FastAPI's background tasks properly
        import asyncio
        asyncio.create_task(design_architecture())
    else:
        project.status = ProjectStatus.REQUIREMENT_GATHERING
        project.audit_log.append({
            "timestamp": datetime.now().isoformat(),
            "action": "prd_rejected",
            "details": req.feedback
        })
    
    return {"status": project.status}

@app.post("/projects/{project_id}/architecture-review")
async def review_architecture(project_id: str, req: ArchitectureReviewRequest):
    """Step 4: Review architecture"""
    if project_id not in projects:
        raise HTTPException(status_code=404, detail="Project not found")
    project = projects[project_id]
    
    if req.approved:
        project.status = ProjectStatus.CODING
        # Trigger coding
        async def start_coding():
            code = await simulate_coding(project.architecture)
            project.code = code
            project.status = ProjectStatus.TEST_CASE_GENERATION
            project.audit_log.append({
                "timestamp": datetime.now().isoformat(),
                "action": "coding_completed",
                "details": f"Generated {len(code)} files"
            })
            # Also generate test cases
            tcs = await simulate_test_case_generation(project.prd)
            project.test_cases = tcs
            project.status = ProjectStatus.TEST_CASE_REVIEW
            project.audit_log.append({
                "timestamp": datetime.now().isoformat(),
                "action": "test_cases_generated",
                "details": f"Generated {len(tcs)} test cases"
            })
        
        asyncio.create_task(start_coding())
    else:
        project.status = ProjectStatus.ARCHITECTURE_DESIGN
        project.audit_log.append({
            "timestamp": datetime.now().isoformat(),
            "action": "architecture_rejected",
            "details": req.feedback
        })
    
    return {"status": project.status}

@app.post("/projects/{project_id}/testcase-review")
async def review_test_cases(project_id: str, req: TestCaseReviewRequest):
    """Step 5: Review test cases"""
    if project_id not in projects:
        raise HTTPException(status_code=404, detail="Project not found")
    project = projects[project_id]
    
    if req.approved:
        project.status = ProjectStatus.TESTING
        # Trigger testing
        async def run_tests():
            report = await simulate_testing(project.code, project.test_cases)
            project.test_reports.append(report)
            
            if report.pass_rate == 100:
                project.status = ProjectStatus.COMPLETED
                project.audit_log.append({
                    "timestamp": datetime.now().isoformat(),
                    "action": "all_tests_passed",
                    "details": "Project completed successfully"
                })
            else:
                # Create bugs for failed tests
                for failed_id in report.failed_tests:
                    bug = BugRecord(
                        id=str(uuid.uuid4()),
                        description=f"Test {failed_id} failed",
                        failed_test_id=failed_id,
                        status="open"
                    )
                    project.bugs.append(bug)
                project.status = ProjectStatus.BUG_FIXING
                project.audit_log.append({
                    "timestamp": datetime.now().isoformat(),
                    "action": "bugs_detected",
                    "details": f"{len(report.failed_tests)} bugs found"
                })
                # Trigger bug fixing
                asyncio.create_task(fix_bugs(project))
        
        asyncio.create_task(run_tests())
    else:
        project.status = ProjectStatus.TEST_CASE_GENERATION
        project.audit_log.append({
            "timestamp": datetime.now().isoformat(),
            "action": "test_cases_rejected",
            "details": req.feedback
        })
    
    return {"status": project.status}

async def fix_bugs(project: Project):
    """Step 6: Fix bugs and retest"""
    for bug in project.bugs:
        if bug.status == "open":
            project.code = await simulate_bug_fixing(bug, project.code)
            project.audit_log.append({
                "timestamp": datetime.now().isoformat(),
                "action": "bug_fixed",
                "details": f"Fixed bug {bug.id}: {bug.fix_method} in {bug.program_name}"
            })
    
    # Retest
    project.status = ProjectStatus.TESTING
    report = await simulate_testing(project.code, project.test_cases)
    project.test_reports.append(report)
    
    if report.pass_rate == 100:
        project.status = ProjectStatus.COMPLETED
        project.audit_log.append({
            "timestamp": datetime.now().isoformat(),
            "action": "all_tests_passed",
            "details": "Project completed after bug fixes"
        })
    else:
        # Continue bug fixing loop
        for failed_id in report.failed_tests:
            if not any(b.failed_test_id == failed_id and b.status == "open" for b in project.bugs):
                bug = BugRecord(
                    id=str(uuid.uuid4()),
                    description=f"Test {failed_id} failed after fix",
                    failed_test_id=failed_id,
                    status="open"
                )
                project.bugs.append(bug)
        project.status = ProjectStatus.BUG_FIXING
        # Recursive fix
        asyncio.create_task(fix_bugs(project))

@app.get("/projects/{project_id}")
async def get_project(project_id: str):
    """Get project status and artifacts"""
    if project_id not in projects:
        raise HTTPException(status_code=404, detail="Project not found")
    return projects[project_id]

@app.get("/projects/{project_id}/artifacts/{artifact_type}")
async def get_artifact(project_id: str, artifact_type: str):
    """Get specific artifact (prd, architecture, code, test_report)"""
    if project_id not in projects:
        raise HTTPException(status_code=404, detail="Project not found")
    project = projects[project_id]
    
    if artifact_type == "prd":
        return project.prd
    elif artifact_type == "architecture":
        return project.architecture
    elif artifact_type == "code":
        return project.code
    elif artifact_type == "test_report":
        return project.test_reports[-1] if project.test_reports else None
    else:
        raise HTTPException(status_code=400, detail="Invalid artifact type")

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}
