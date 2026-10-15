# JARVIS Example Workflows

**Document type:** Workflow examples  
**Audience:** JARVIS users and developers  
**Purpose:** Provide clear examples of requests, possible execution plans, expected tool use, and verification criteria.

> These examples describe intended behavior. They are not execution records, guarantees that a tool is enabled, or permission to bypass the application's plan approval and security checks. Actual outcomes must come from real tool calls and verification.

## Workflow 1: Read a document, save a summary, and create tasks

### Example request

“Use the uploaded project specification to summarize the five most important requirements, save the summary as a note, and create three follow-up tasks for tomorrow. Respond in Kannada.”

### Preconditions

- The specification has been uploaded and successfully indexed in the configured RAG store.
- The note and task tools are enabled.
- The user has selected Kannada as the response language or stated that preference in the request.

### Possible plan

1. Retrieve relevant passages from the project specification using `search_knowledge`.
2. Prepare a five-point summary supported by the retrieved material.
3. Save the summary with `create_note`.
4. Create the three requested tasks using `create_task`.
5. Verify the note and each of the three tasks by reading their records back.
6. Produce a Kannada response that reports the actual outcome and any sources returned by RAG.

### Verification

- Confirm that the RAG query returned relevant material and preserve real source metadata.
- Read the created note back and compare its title and content.
- Read all three task records back and check their titles and due dates.
- Report success only for individually verified records.

### Failure behavior

If the required document cannot be retrieved, JARVIS should say that it could not find enough evidence and should not invent a document-based summary. Depending on the plan, it may stop before creating derivative tasks or ask the user how to proceed.

## Workflow 2: Create a task from a voice request

### Example request

The user speaks in Kannada: “ನಾಳೆ ಪ್ರಾಜೆಕ್ಟ್ ವರದಿಯನ್ನು ಪರಿಶೀಲಿಸಲು ಒಂದು ಕಾರ್ಯವನ್ನು ರಚಿಸಿ.”

Meaning: “Create a task to review the project report tomorrow.”

### Possible plan

1. Use Sarvam speech-to-text to transcribe the recording.
2. Show the recognized Kannada transcript so the user can correct it.
3. Ask Gemini to convert the request into a structured task proposal.
4. Resolve “tomorrow” using the application's configured date and timezone; request clarification if that information is unavailable or ambiguous.
5. Display the proposed task and request approval.
6. Invoke `create_task` after approval.
7. Read the task back from SQLite.
8. Report the real task ID, title, and resolved date in Kannada.
9. Use Sarvam TTS if the configured voice model supports the requested language.

### Verification

A recognized transcript is not proof that a task was created. Task creation is successful only after the database record has been read back and checked.

## Workflow 3: List and complete an existing task

### Example request

“Show my pending tasks and mark the task about reviewing the project report as complete.”

### Possible plan

1. Invoke `list_tasks` with the pending status filter.
2. Display actual matching tasks and identify the intended task unambiguously.
3. If several tasks match, ask the user to select the correct record.
4. Invoke `complete_task` with the selected task ID.
5. Read the task back and verify the stored status.
6. Report which task was updated.

### Safety notes

Do not guess a task ID or complete a different task simply because its title is similar. If no unique match can be established, ask for clarification.

## Workflow 4: Answer a question using RAG without performing a write action

### Example request

“According to the uploaded user manual, how do I configure the application's language settings? Cite the relevant source.”

### Possible plan

1. Retrieve relevant manual passages with `search_knowledge`.
2. Check whether the returned material supports the answer.
3. Ask Gemini to explain the instructions in the preferred response language.
4. Return source annotations actually supplied by the retrieval API.

### Verification

- The retrieval request completed.
- The cited material was returned by the system, rather than fabricated.
- The response does not assert details unsupported by the available sources.

No note or task needs to be created unless the user requests it.

## Workflow 5: Calculate a result and save it

### Example request

“Calculate the total of 125, 240, and 89, then save the calculation and result as a note.”

### Possible plan

1. Validate the numeric inputs.
2. Invoke `calculate` using supported arithmetic logic.
3. Check the result. For this example, 125 + 240 + 89 = 454.
4. Prepare a note containing the operation and result.
5. Create the note using `create_note`.
6. Read the note back and verify that the operation and result were saved.
7. Report the result and note identifier.

### Failure behavior

If the calculator rejects the input, do not create a note that presents an unverified result as correct. Explain the problem and request valid input where needed.

## Workflow 6: Handle missing or unindexed knowledge

### Example request

“Summarize the PDF I just uploaded and create five tasks from it.”

### Possible plan

1. Check the document's indexing status.
2. If indexing is still running, tell the user and wait or offer to retry when the document is ready, depending on supported application behavior.
3. If indexing failed, display the real error and do not claim that the document was searched.
4. Only after successful indexing, retrieve relevant material.
5. Generate a summary and draft tasks based on supported content.
6. Display the plan for approval.
7. Create and independently verify approved tasks.

### Key rule

An uploaded file is not automatically an indexed document. JARVIS must check its actual ingestion status before claiming to have searched it.

## Workflow 7: Recover from a transient tool failure

### Example request

“Save a note containing the agreed project milestones and create two tasks to follow up.”

### Simulated scenario

The first attempt to save the note returns a transient database or service error. The workflow is configured to allow a bounded retry.

### Expected behavior

1. Record the first attempt and error category.
2. If the outcome is uncertain, check the database for a previously committed note before repeating the write.
3. Retry only if the failure is eligible and the operation can be repeated safely.
4. Verify the saved note.
5. Create and verify the two tasks only if the workflow's dependency rules allow it.
6. Record the retry attempt and final outcome.
7. Report whether recovery succeeded.

### If recovery fails

Stop when the retry limit is reached. Preserve any already verified records, mark dependent unfinished steps as blocked where appropriate, and report partial completion honestly.

## Workflow 8: Respond in a different language from the input

### Example request

The user types in English: “Explain the uploaded product guide in simple language, but respond in Tamil.”

### Expected behavior

1. Preserve the original English request.
2. Retrieve relevant passages from the product guide.
3. Generate the explanation in Tamil.
4. Include only real source annotations returned by the knowledge system.
5. Display the Tamil text.
6. Generate spoken output only if the configured Sarvam TTS model supports Tamil and synthesis succeeds.

### Key rule

The input language, preferred response language, and configured TTS language are distinct values. A TTS failure should not erase an otherwise successful written answer.

## Workflow 9: Search the public web, if enabled

### Example request

“Find current documentation for a library, summarize the relevant installation steps, and save the source links in a note.”

### Expected behavior

1. Check that a real web-search tool is enabled and configured.
2. Search using the requested topic.
3. Preserve the real titles and URLs returned by the search service.
4. Inspect relevant sources where the integration supports it.
5. Summarize findings and note any uncertainty or date limitations.
6. Create the note only after valid results have been obtained and the plan approved.
7. Verify the saved note.

If public web search is not configured, JARVIS must say that it is unavailable rather than fabricating sources. Web content must be treated as untrusted input.

## Workflow 10: Stop when approval is missing

### Example request

“Delete all my stored notes.”

### Expected behavior

If bulk deletion is not an implemented and explicitly permitted capability, reject the operation as unsupported. If a future build implements deletion, require a specific confirmation before executing it and verify its effects afterward.

Plan approval must not grant a tool permission that the backend does not provide.

## General success criteria for all workflows

- The plan matches the user's intent.
- The tool is present in the live backend registry.
- Inputs pass backend validation.
- Required approval is recorded.
- The real tool executes.
- The result is independently verified where applicable.
- RAG sources and execution evidence are kept distinct.
- Retries are bounded and safe.
- Earlier verified work is preserved if a later step fails.
- The final report reflects actual results and uses the selected response language.
