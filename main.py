from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import time
from pydantic import BaseModel

app = FastAPI(
    title="TODO API",
    version="1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    print(f"Request to {request.url.path} processed in {process_time:.4f} seconds")
    return response


@app.get("/add")
def add_numbers(a: int, b: int):
    return {"result": a + b}


class TaskCreate(BaseModel):
    title: str
    description: str


class TaskUpdate(TaskCreate):
    title: str
    description: str
    done: bool = False


class Task(TaskUpdate):
    id: int


tasks: list[Task] = []
next_id = 1


@app.get("/tasks", response_model=list[Task])
async def get_tasks():
    return tasks


@app.get("/tasks/{task_id}", response_model=Task)
async def get_task(task_id: int):
    for t in tasks:
        if t.id == task_id:
            return t
    raise HTTPException(status_code=404, detail="Task not found")


@app.post("/tasks", response_model=Task, status_code=201)
async def create_task(task: TaskCreate):
    global next_id
    new_task = Task(
        id=next_id,
        title=task.title,
        description=task.description
    )
    tasks.append(new_task)
    next_id += 1
    return new_task


@app.put("/tasks/{task_id}", response_model=Task)
async def update_task(task_id: int, updated: TaskUpdate):
    for idx, t in enumerate(tasks):
        print(idx, t.id, task_id)
        if t.id == task_id:
            tasks[idx] = Task(
                id=t.id,
                title=updated.title,
                description=updated.description,
                done=updated.done,
            )
            return tasks[idx]
    raise HTTPException(status_code=404, detail="Task not found")


@app.delete("/tasks/{task_id}", status_code=204)
async def delete_task(task_id: int):
    for t in tasks:
        if t.id == task_id:
            tasks.remove(t)
            return
    raise HTTPException(status_code=404, detail="Task not found")
