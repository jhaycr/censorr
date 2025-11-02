// Danger rules enforcing task ledger hygiene and commit traceability
const { danger, fail, warn } = require('danger');

// Ensure every commit references at least one task ID (e.g., T001)
const taskPattern = /T\d{2,}/;
const skipPattern = /\[skip-task-check\]/i;
const commitsMissingTasks = danger.git.commits.filter((commit) => !taskPattern.test(commit.message) && !skipPattern.test(commit.message));
if (commitsMissingTasks.length > 0) {
  const list = commitsMissingTasks.map((commit) => `- ${commit.sha.slice(0, 7)} ${commit.message}`).join("\n");
  fail(`Commit messages must reference task IDs (e.g., T001). Offending commits:\n${list}`);
}

// Guard the immutable tasks ledger: allow only append or marking complete with ✅
const tasksFiles = danger.git.fileMatch('specs/**/tasks.md');
if (tasksFiles.deleted.length > 0) {
  fail(`Tasks ledgers cannot be deleted: ${tasksFiles.deleted.join(', ')}`);
}

const checkTasksFile = async (path) => {
  const diff = await danger.git.diffForFile(path);
  if (!diff) {
    return;
  }
  const added = diff.added.split('\n').map((line) => line.trim()).filter(Boolean);
  const removed = diff.removed.split('\n').map((line) => line.trim()).filter(Boolean);

  const disallowed = removed.filter((line) => {
    if (!line) {
      return false;
    }
    // Allow marking complete by appending ✅ (the new line should start with the old text)
    const hasCompletion = added.some((addedLine) => addedLine.startsWith(line) && addedLine.includes('✅'));
    return !hasCompletion;
  });

  if (disallowed.length > 0) {
    const preview = disallowed.map((line) => `- ${line}`).join('\n');
    fail(`Tasks files must be append-only (or mark items complete with ✅). Review changes in ${path}:\n${preview}`);
  }
};

tasksFiles.edited.forEach((path) => {
  schedule(async () => {
    await checkTasksFile(path);
  });
});

if (tasksFiles.created.length > 0) {
  const createdList = tasksFiles.created.join(', ');
  warn(`New tasks ledgers detected (verify numbering continuity): ${createdList}`);
}
