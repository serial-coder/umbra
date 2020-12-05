import os
import logging
import asyncio
from datetime import datetime


logger = logging.getLogger(__name__)


class Loader:
    def __init__(self):
        self._files = []

    def _get_filepath(self, root, filename, full_path):
        """Adds filepath (if relative or not) to self._files list

        Arguments:
            root {string} -- Root folder where filename is located
            filename {string} -- Name of the file listed in root
            full_path {bool} -- Flag for absolute file path or not
        """

        if full_path:
            p = os.path.join(root, filename)
            file_path = os.path.abspath(p)
            self._files.append(file_path)
        else:
            self._files.append(filename)

    def _load_file(self, root, f, prefix, suffix, full_path):
        """Checks file suffix and prefix to add to files loaded

        Arguments:
            root {string} -- Root dir in file path
            f {string} -- Filename
            prefix {string} -- Prefix needed for filename
            suffix {string} -- Suffix needed for filename
            full_path {bool} -- If absolute or realtive file path must be loaded
        """
        prefix_ok = f.startswith(prefix) if prefix else True
        suffix_ok = f.endswith(suffix) if suffix else True

        if prefix_ok and suffix_ok:
            self._get_filepath(root, f, full_path)
        else:
            pass
            # logger.debug(f"Could not get file {f} path by suffix {suffix} or prefix {prefix}")

    def files(self, folder=None, prefix=None, suffix=None, full_path=False):
        """Gets all the names of files in a folder (not subfolders)

        Keyword Arguments:
            folder {string} -- Path to the folder name (default: {None})
            prefix {string} -- Filter files that begin with prefix (default: {None})
            suffix {string} -- Filter files that end with suffix (default: {None})
            full_path {bool} -- If files should be in full/abs or relative path (default: {False})

        Returns:
            [list] -- All the file names inside a folder
        """
        logger.debug(
            f"Loading files in folder {folder} - "
            f"prefix {prefix} and suffix {suffix} - full/abs path {full_path}"
        )

        try:
            for root, _, files in os.walk(folder):
                for f in files:
                    self._load_file(root, f, prefix, suffix, full_path)
                break

        except Exception as e:
            logger.debug(f"Loading files exception - {e}")

        finally:
            logger.debug(f"Loaded files: {self._files}")
            return self._files


class Handler:
    def __init__(self):
        self._tasks = {}

    def _check_finish(self, uid, finish, timeout):
        """Checks if task has reached timeout

        Arguments:
            uid {string} -- Unique identifier of task
            finish {int} -- Time in seconds that task must end
            timeout {int} -- Time in seconds that task is taking

        Returns:
            bool -- A flag True if timeout is bigger than finish, False otherwise
        """
        if finish == 0:
            pass
        else:
            if finish <= timeout:
                logger.debug(f"Task {uid} finish timeout {timeout}")
                return True
            else:
                logger.debug(f"Task {uid} timeout {timeout}")
        return False

    async def _check_task(self, uid, task, duration):
        """Checks task if finished to obtain output result

        Arguments:
            uid {string} -- Unique identifier of call
            task {coroutine} -- Task coroutine of command call uid
            duration {int} -- Expected duration of task

        Returns:
            int -- Amount of time in seconds that task took to be executed
        """
        if duration != 0:
            logger.debug(f"Waiting for task {uid} duration")
            await asyncio.sleep(duration)
            logger.debug(f"Task {uid} duration ended")
            task_duration = duration
        else:
            logger.debug(f"Waiting for task {uid} (normal execution)")
            start = datetime.now()
            _, _ = await asyncio.wait({task})
            stop = datetime.now()
            task_duration = (stop - start).total_seconds()

        return task_duration

    async def _check_task_result(self, uid, task):
        """Retrieves task output result

        Arguments:
            uid {string} -- Unique identifier of task/call
            task {coroutine} -- Task coroutine of command call uid

        Returns:
            dict -- Output of task command executed by call
        """
        logger.debug(f"Checking Task {uid}")
        if task.done():
            logger.debug(f"Result Task {uid} Done")
            result = task.result()
        else:
            logger.debug(f"Cancel Task {uid} Pending")
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                logger.debug(f"Task {uid} cancelled")
            finally:
                result = None

        logger.debug(f"Task result: {result}")
        return result

    async def _schedule(self, uid, call, sched):
        """Executes a call uid to the command cmd following the
        scheduling (time) properties of sched

        Arguments:
            uid {string} -- The call unique id
            cmd {string} -- The command to be called/executed
            sched {dict} -- Contains keys that determine the timely manner
            that the cmd is going to be called

        Returns:
            list -- A list of results of the called cmd according to sched parameters
        """
        logger.debug(f"Scheduling call uid {uid}")
        logger.debug(f"Schedule parameters: {sched}")
        loop = asyncio.get_event_loop()
        results = []

        begin = sched.get("from", 0)
        finish = sched.get("until", 0)
        duration = sched.get("duration", 0)
        repeat = sched.get("repeat", 0)
        interval = sched.get("interval", 0)

        timeout = 0
        task_duration = 0
        repeat = 1 if repeat == 0 else repeat

        try:
            for _ in range(repeat):

                await asyncio.sleep(begin)
                begin = interval

                if asyncio.iscoroutine(call):
                    logger.debug(f"Call is coroutine")
                    aw = call
                else:
                    logger.debug(f"Call is not coroutine")
                    aw = call()

                task = loop.create_task(aw)
                logger.debug(f"Task {uid} created {task}")

                task_duration = await self._check_task(uid, task, duration)
                result = await self._check_task_result(uid, task)

                if result:
                    logger.debug(f"Task {uid} result available")
                    results.append(result)
                else:
                    logger.debug(f"Task {uid} result unavailable")

                timeout += task_duration + interval
                if self._check_finish(uid, finish, timeout):
                    break
        except asyncio.CancelledError:
            logger.debug(f"Cancelling task {uid}")

            try:
                if not task.done():
                    task.cancel()
                    await task

            except asyncio.CancelledError:
                logger.debug(f"Task {uid} cancelled")

        finally:
            return results

    async def _build(self, calls):
        """Builds list of command calls as coroutines to be
        executed by asyncio loop

        Arguments:
            calls {list} -- List of command calls

        Returns:
            list -- Set of coroutines scheduled to be called
        """
        logger.debug(f"Building calls into coroutines")
        aws = {}
        for uid, (call, call_sched) in calls.items():
            aw = self._schedule(uid, call, call_sched)
            aws[uid] = aw

        return aws

    async def run(self, calls):
        """Executes the list of calls as coroutines
        returning their results

        Arguments:
            calls {list} -- Set of commands to be scheduled and called as subprocesses

        Returns:
            dict -- Results of calls (stdout/stderr) indexed by call uid
        """
        results = {}

        aws = await self._build(calls)

        logger.debug(f"Running built coroutines")
        tasks = await asyncio.gather(*(aws.values()), return_exceptions=True)

        calls_ids = list(calls.keys())
        counter = 0

        for aw in tasks:
            uid = calls_ids[counter]

            if isinstance(aw, Exception):
                logger.debug(f"Could not run _schedule {calls[uid]} - exception {aw}")
            else:
                if aw:
                    results[uid] = aw.pop()
                else:
                    results[uid] = {}

            counter += 1

        return results

    async def start(self, calls):
        """Executes the list of calls as coroutines
        returning their results

        Arguments:
            calls {list} -- Set of commands to be scheduled and called as subprocesses

        Returns:
            dict -- Results of calls (stdout/stderr) indexed by call uid
        """
        results = {}

        aws = await self._build(calls)

        logger.debug(f"Starting tasks")
        for uid, aw in aws.items():
            logger.debug(f"Starting task {uid}")
            uid_task = asyncio.create_task(aw)
            self._tasks[uid] = uid_task

            if uid_task:
                results[uid] = "ok"
            else:
                results[uid] = "error"

        logger.debug(f"Finished tasks start")
        return results

    async def stop(self, calls):
        results = {}

        aws = []

        logger.debug(f"Stopping tasks")

        logger.debug(f"Running tasks - {self._tasks.items()}")
        logger.debug(f"Stopping tasks - {calls.keys()}")

        for uid in calls.keys():
            task = self._tasks.get(uid, None)

            if task:
                logger.debug(f"Stopping task {uid}")
                task.cancel()
                aws.append(task)

        logger.debug(f"Waiting tasks stop")
        tasks = await asyncio.gather(*aws, return_exceptions=True)

        calls_ids = list(calls.keys())
        counter = 0

        for aw in tasks:
            uid = calls_ids[counter]

            if isinstance(aw, Exception):
                logger.debug(f"Could not run _schedule {calls[uid]} - exception {aw}")
                results[uid] = "error"
            else:
                results[uid] = "ok"

            counter += 1

        logger.debug(f"Finished tasks stop")
        return results
