import asyncio
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor

from fastapi import FastAPI, Request, Response, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

class TaskModel(Base):
    __tablename__ == "tasks"



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

@app.get("/async_task")
async def async_task():
    await asyncio.sleep(60)
    return {"message": "ok"}


@app.get("/background_task")
async def background_task(background_task: BackgroundTasks):
    def slow_time():
        import time

        time.sleep(10)
        print("OK!")

    background_task.add_task(slow_time)
    return {"message": "task started"}


excutor = ThreadPoolExecutor(max_workers=2)
executor = ProcessPoolExecutor(max_workers=2)

def blocking_io_task():
    import time

    time.sleep(60)
    return "ok"

@app.get("/thread_pool_sleep")
async def thread_pool_sleep():
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(excutor, blocking_io_task)
    return {"message": result}

def heavy_func(n: int):
    result = 0
    for i in range(n):
        result += i * i
    return result

@app.get("/cpu_task")
async def cpu_task(n: int = 10_000_000_000):
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(excutor, heavy_func, n)
    return {
        "message": result
    }