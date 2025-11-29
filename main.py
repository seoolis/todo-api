import asyncio
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor

from fastapi import FastAPI, Request, Response, HTTPException, BackgroundTasks, Depends, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from sqlmodel import SQLModel, Field
from sqlalchemy import Column, Integer, String, Boolean, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker
from starlette.websockets import WebSocketDisconnect

Base = declarative_base()
engine = create_async_engine(
    "sqlite+aiosqlite:///./tasks.db"
)
DBSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=AsyncSession)


class TaskModel(SQLModel, table=True):
    __tablename__ = 'tasks'

    id: int | None = Field(primary_key=True)
    title: str
    description: str
    done: bool = False


# Base.metadata.create_all(bind=engine)


async def get_db():
    db = DBSession()
    try:
        yield db
    finally:
        await db.close()


app = FastAPI(
    title="TODO API",
    version="1.0"
)


@app.on_event("startup")
async def on_startup():
    async with engine.begin() as conn:
        await conn.run_sync(
            SQLModel.metadata.create_all
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


@app.get("/tasks", response_model=list[TaskModel])
async def get_tasks(
        db: DBSession = Depends(get_db)
):
    stmt = select(TaskModel)
    result = await db.execute(stmt)
    return result.scalars()


@app.get("/tasks/{task_id}", response_model=TaskModel)
async def get_task(task_id: int, db: DBSession = Depends(get_db)):
    task = await db.get(TaskModel, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@app.post("/tasks", response_model=Task, status_code=201)
async def create_task(
        task: TaskCreate,
        db: DBSession = Depends(get_db)
):
    new_task = TaskModel(
        title=task.title,
        description=task.description,
    )

    db.add(new_task)
    await db.commit()
    await db.refresh(new_task)
    return new_task


@app.put("/tasks/{task_id}", response_model=TaskModel)
async def update_task(
        task_id: int,
        updated: TaskUpdate,
        db: DBSession = Depends(get_db)
):
    task = await db.get(TaskModel, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    for key, value in updated.model_dump().items():
        setattr(task, key, value)

    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


@app.delete("/tasks/{task_id}", status_code=204)
async def delete_task(
        task_id: int,
        db: DBSession = Depends(get_db)):
    obj = await db.get(TaskModel, task_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Task not found")
    await db.delete(obj)
    await db.commit()


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

# тут будет парсер

from playwright.async_api import async_playwright


class CitilinkParser:

    async def start(self):
        playwright = await async_playwright().start()
        self.browser = await playwright.chromium.launch(headless=False)
        context = await self.browser.new_context()
        self.page = await context.new_page()

@app.get("/parser")
async def parser(background_task: BackgroundTasks):
    def func(x):
        return x
    category_url = "https://www.citilink.ru/catalog/smartfony"
    background_task.add_task(func, category_url)
    return {
        "message": "Парсер запущен в фоне"
    }


# а тут вебсокет

class ConnectionManadger:
    def __init__(self):
        self.active_connection: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connection.append(websocket)

    async def handle(self, data, websocket):
        if data == "spec":
            await websocket.send_text("SPEC OK!")
        elif data == "close":
            await self.disconnect(websocket)
        else:
            await websocket.send_text(data * 10)

    async def disconnect(self, websocket: WebSocket):
        await websocket.close()
        self.active_connection.remove(websocket)

manager = ConnectionManadger()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)

    async def tick():
        while True:
            await websocket.send_text('FOO!')
            await asyncio.sleep(10)
    asyncio.create_task(tick())

    try:
        while True:
            data = await websocket.receive_text()
            await manager.handle(data, websocket)

    except WebSocketDisconnect:
        await manager.disconnect(websocket)