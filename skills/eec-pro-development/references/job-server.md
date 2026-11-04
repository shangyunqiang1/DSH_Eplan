# Job Server in practice — recipes, triggers, REST, timing

Field notes from running EEC Pro generation unattended through the Job Server (EEC Pro 2025.3 workers).
The official reference is `refjobserver` / `eecjobserver` / `tutjobs` in the doc index. This page covers
what those pages leave implicit.

## Recipe (`.jmx`) anatomy

```xml
<?xml version="1.0"?>
<jobdefinition name="=trigger.fileName.split('\\.').first() + '_machine'"   <!-- name MAY be a formula -->
    continueOnError="true"
    model="\\server\share\resources\FAMILY\MACHINE\v12\EOX\Model.eox"     <!-- fixed per recipe -->
    failedMailRecipients="someone@example.com">
  <fileTrigger>
    <incomingFolder value="\\server\share\queue\machine\in" />
    <outputFolder   value="\\server\share\out" />      <!-- literal path: NO formulas -->
    <failedFolder   value="\\server\share\error" />
    <filter value="*.json" />
  </fileTrigger>
  <actions>
    <action name="Library.Package.SomeAction" arguments="=List{trigger.filePath}" />
    <action name="Engineering.SaveObjectCommand" arguments="=List{absRef('NewProject.Mechatronic')}" />
    <action name="JobServer.SetProgressMessageCommand" arguments="List{'machine'}" />
  </actions>
</jobdefinition>
```

- **`name` accepts a formula.** `outputFolder` does not: a formula there is taken as a literal path relative
  to the worker. To group results, put a common prefix in the job *name*. The result folder is
  `<outputFolder>\<jobName>`.
- **`model` is fixed per recipe.** One recipe per model or version. Switching models inside a job (forceful
  EOX import) is fragile.
- **`continueOnError="true"`** keeps running the actions after a failure. Use it when a final bookkeeping
  action must always run. It does not cover every failure: a command that throws inside the generation
  sequence can still end the job.
- **`webserviceTrigger`** with `<jsonAlias value="Root"/>` accepts a body like `{"Root": …}` (your client's
  top-level key) without a `json` wrapper. The body is then available as `trigger.json`.
- **Trigger variables** seen in logs:
  - `trigger.filePath`, `trigger.fileName` (no extension), `trigger.fullFileName`, `trigger.fileExtension`;
  - `trigger.jobName`;
  - `trigger.additionalResultsDir` (on the worker's local disk), `trigger.outputFolder`, `trigger.failedFolder`;
  - `trigger.json` (web service only).
- **Argument lists:** `arguments="=List{…}"` is evaluated as a formula. `List{}` passes nothing (for
  commands without arguments).

## Deploying recipe changes

- **The Job Server does not pick up an edited `.jmx` by itself.** Recipes must be reloaded or updated in the
  Job Server after every change. A recipe whose file was deleted keeps its trigger alive until then.
- **Two recipes watching the same `incomingFolder` race for the same file.** Remove the old one (and reload)
  before reusing a folder for a probe.
- **A watched folder that does not exist** produces a recurring `FileTriggerMissingReadPermissions` error in
  the logs.
- **While a job runs, the `fileTrigger` moves the file to `<incomingFolder>\<GUID>\<file>`.**
  `trigger.filePath` points there, not to the original location.

## Workers and orchestration

- **Count the workers first** (`GET /api/workers`). With one worker, a parent job that waits for its child
  jobs deadlocks, because it occupies the only worker. Design parents that *dispatch and finish*: they
  write one input file per child into the queue folders.
- **Each job's project is generated in the worker's local workspace**
  (`…\EEC\<version>\workspace\<Project>\<random>\…`). It is copied to `<outputFolder>\<jobName>\results` only
  *after* the job ends, so a later action in the same job cannot find it on the share. If another job needs
  an artifact, publish it explicitly from a post-generation script (see `groovy-actions.md`, ScriptArguments).
- **The copy after the job takes the whole project database** (~100 MB for a ~40-page project). Budget disk
  space on the output share.

## Coordinating jobs through files (no external service)

When several jobs must agree on something, such as "the last machine of a batch closes it":
- **Use `File.createNewFile()` on the share** (atomic create-if-absent). The job that creates
  `state\turn\<k>` owns turn *k*. Start probing at `listing.length + 1`: a stale listing can only be short,
  never long.
- **Write files as `<name>.<uuid>.tmp` and rename them**, retrying the rename a few times. A `*.json` filter
  never sees half-written files, and two jobs writing the same target do not clobber each other's temp file.
- **Never decide by "newest file" or by an SMB directory count** once more than one worker can run. Pass
  exact paths instead.

## REST API (worker host, e.g. `http://host:8686`)

| Call | Use |
|---|---|
| `POST /api/jobs/request/<recipe>` + JSON body | Start a web-service-triggered job. Returns `id` and `status: Queued` |
| `GET /api/jobs/<id>` | `status`, `jobName`, `executedOnWorker` |
| `GET /api/jobs` | `{ totalSize, jobs: [...] }` — filter by `jobName` prefix client-side |
| `GET /api/logs` | All log trees: `jobId`, `logGroup`, `message`, `startTime`/`endTime` (ms), `children` |
| `GET /api/workers` | Worker list |

- **Timing lives in `/api/logs`, not in the `.log` file.** The `.log` in a job's output folder has no
  timestamps. Each log node has start and end times, so the tree of a job gives the duration of every recipe
  action. Download it once and filter by `jobId` locally: the response is tens of MB.
- **Warnings raised from Groovy** (`UserMessageCollector.addWarning`) appear as children of the action. They
  are the best way to trace what an action decided.

## Where generation time goes (measured)

For machine-level models of roughly 15–40 pages:

| Phase | Typical share |
|---|---|
| Reading JSON and setting parameters | < 1 s |
| `GenerateEcadStructure` (EEC side) | ~5 s |
| Empty P8 project and script start-up | ~5 s |
| **Page generation in P8 (macro insertion)** | **the bulk: 1–5 s per page, depending on how many macros a page receives** |
| Exporting the project to `.emp` | ~4 s |
| Copying results to the share | 2–4 s |

- **Cost follows the number of macro insertions, not the page count.** A model with many small window
  macros is slower per page than one with a few page macros.
- **Inserting `.emp` page macros into one large project costs a constant ~0.3 s/page on a desktop.** It does
  not grow as the project grows. Pages without devices are almost free.
- **Worker hardware dominates.** The same insertion loop ran 2–3× slower on a VM worker than on a desktop.
  Check the worker (CPU, RAM, disk) before optimizing scripts.
- **Measure before optimizing.** Use the `/api/logs` durations per action, plus file timestamps written at
  known points: a marker file at job start, and the script start and export end recorded in a small JSON by
  the post-generation script.
