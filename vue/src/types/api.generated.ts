// 由 npm run generate:api 自动生成，请勿手工修改。
export interface paths {
  "/api/v1/me": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };

    get: operations["get_me_api_v1_me_get"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/auth/token": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;

    post: operations["login_api_v1_auth_token_post"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/projects": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };

    get: operations["list_projects_api_v1_projects_get"];
    put?: never;

    post: operations["create_project_api_v1_projects_post"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/projects/{project_id}": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };

    get: operations["get_project_api_v1_projects__project_id__get"];
    put?: never;
    post?: never;

    delete: operations["delete_project_api_v1_projects__project_id__delete"];
    options?: never;
    head?: never;

    patch: operations["update_project_api_v1_projects__project_id__patch"];
    trace?: never;
  };
  "/api/v1/projects/{project_id}/tasks": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };

    get: operations["list_tasks_api_v1_projects__project_id__tasks_get"];
    put?: never;

    post: operations["create_task_api_v1_projects__project_id__tasks_post"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/projects/{project_id}/tasks/{task_id}": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };

    get: operations["get_task_api_v1_projects__project_id__tasks__task_id__get"];
    put?: never;
    post?: never;

    delete: operations["delete_task_api_v1_projects__project_id__tasks__task_id__delete"];
    options?: never;
    head?: never;

    patch: operations["update_task_api_v1_projects__project_id__tasks__task_id__patch"];
    trace?: never;
  };
  "/api/v1/projects/{project_id}/documents": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };

    get: operations["list_documents_api_v1_projects__project_id__documents_get"];
    put?: never;

    post: operations["create_document_api_v1_projects__project_id__documents_post"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/projects/{project_id}/documents/{document_id}/retry": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;

    post: operations["retry_document_api_v1_projects__project_id__documents__document_id__retry_post"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/projects/{project_id}/documents/{document_id}": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    post?: never;

    delete: operations["delete_document_api_v1_projects__project_id__documents__document_id__delete"];
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/projects/{project_id}/knowledge": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };

    get: operations["knowledge_info_api_v1_projects__project_id__knowledge_get"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/projects/{project_id}/knowledge/questions": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;

    post: operations["ask_question_api_v1_projects__project_id__knowledge_questions_post"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/projects/{project_id}/planning": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };

    get: operations["planning_info_api_v1_projects__project_id__planning_get"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/projects/{project_id}/planning/proposals": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;

    post: operations["create_proposal_api_v1_projects__project_id__planning_proposals_post"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };

    get: operations["root__get"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/health": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };

    get: operations["health_check_api_v1_health_get"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
}
export type webhooks = Record<string, never>;
export interface components {
  schemas: {
    Body_create_document_api_v1_projects__project_id__documents_post: {
      file: string;
    };

    DocumentListVO: {
      items: components["schemas"]["DocumentVO"][];

      total: number;

      max_documents: number;

      max_size_bytes: number;
    };

    DocumentStatus:
      "queued" | "indexing" | "ready" | "failed" | "deleting" | "delete_failed";

    DocumentVO: {
      id: string;

      project_id: string;

      filename: string;

      size_bytes: number;
      status: components["schemas"]["DocumentStatus"];

      chunk_count: number;

      error_message: string | null;

      created_at: string;

      updated_at: string;
    };

    HTTPValidationError: {
      detail?: components["schemas"]["ValidationError"][];
    };

    HealthVO: {
      status: string;

      service: string;

      timestamp: string;

      ai_mode: string;
    };

    LoginQO: {
      username: string;

      password: string;
    };

    PlanInfoVO: {
      mode: "mock" | "live";

      configured: boolean;

      ready_documents: number;

      task_count: number;
    };

    PlanProposalVO: {
      summary: string;

      assumptions: string[];

      risks: string[];

      tasks: components["schemas"]["TaskDraftVO"][];
    };

    PlanRequestQO: {
      goal: string;
    };

    PlanResultVO: {
      mode: "mock" | "live";
      proposal: components["schemas"]["PlanProposalVO"];

      sources: components["schemas"]["RagSourceVO"][];

      tool_calls: components["schemas"]["ToolCallVO"][];

      board_task_count: number;

      persisted: false;
    };

    ProjectCreateQO: {
      name: string;

      description: string;
    };

    ProjectPageVO: {
      items: components["schemas"]["ProjectVO"][];

      total: number;

      offset: number;

      limit: number;
    };

    ProjectUpdateQO: {
      name?: string | null;

      description?: string | null;
    };

    ProjectVO: {
      id: string;

      owner_id: string;

      name: string;

      description: string;

      created_at: string;

      updated_at: string;
    };

    RagAnswerVO: {
      answer: string;

      sources: components["schemas"]["RagSourceVO"][];

      status: "answered" | "insufficient_evidence";

      mode: "mock" | "live";
    };

    RagInfoVO: {
      mode: "mock" | "live";

      configured: boolean;

      ready_documents: number;
    };

    RagQuestionQO: {
      question: string;
    };

    RagSourceVO: {
      source_id: number;

      document_id: string;

      filename: string;

      chunk_index: number;

      heading: string;

      text: string;
    };

    TaskCreateQO: {
      title: string;

      description: string;

      priority: number;

      status: components["schemas"]["TaskStatus"];

      acceptance_criteria: string;
    };

    TaskDraftVO: {
      draft_id: string;

      title: string;

      description: string;

      priority: number;

      acceptance_criteria: string;

      dependencies: string[];

      source_ids: number[];
    };

    TaskPageVO: {
      items: components["schemas"]["TaskVO"][];

      total: number;

      offset: number;

      limit: number;
    };

    TaskSource: "manual" | "ai";

    TaskStatus: "todo" | "in_progress" | "done";

    TaskUpdateQO: {
      version: number;

      title?: string | null;

      description?: string | null;

      priority?: number | null;
      status?: components["schemas"]["TaskStatus"] | null;

      acceptance_criteria?: string | null;
    };

    TaskVO: {
      id: string;

      project_id: string;

      title: string;

      description: string;

      priority: number;
      status: components["schemas"]["TaskStatus"];

      acceptance_criteria: string;
      source: components["schemas"]["TaskSource"];

      version: number;

      created_at: string;

      updated_at: string;
    };

    TokenVO: {
      access_token: string;

      token_type: "bearer";

      expires_in: number;
      user: components["schemas"]["UserVO"];
    };

    ToolCallVO: {
      name: "search_documents" | "read_task_board";

      status: "success" | "empty";

      item_count: number;
    };

    UserRole: "member" | "reviewer";

    UserVO: {
      id: string;

      username: string;
      role: components["schemas"]["UserRole"];

      created_at: string;

      updated_at: string;
    };

    ValidationError: {
      loc: (string | number)[];

      msg: string;

      type: string;

      input?: unknown;

      ctx?: Record<string, never>;
    };
  };
  responses: never;
  parameters: never;
  requestBodies: never;
  headers: never;
  pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
  get_me_api_v1_me_get: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["UserVO"];
        };
      };
    };
  };
  login_api_v1_auth_token_post: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["LoginQO"];
      };
    };
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["TokenVO"];
        };
      };

      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  list_projects_api_v1_projects_get: {
    parameters: {
      query?: {
        offset?: number;

        limit?: number;
      };
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ProjectPageVO"];
        };
      };

      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  create_project_api_v1_projects_post: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["ProjectCreateQO"];
      };
    };
    responses: {
      201: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ProjectVO"];
        };
      };

      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  get_project_api_v1_projects__project_id__get: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        project_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ProjectVO"];
        };
      };

      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  delete_project_api_v1_projects__project_id__delete: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        project_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      204: {
        headers: {
          [name: string]: unknown;
        };
        content?: never;
      };

      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  update_project_api_v1_projects__project_id__patch: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        project_id: string;
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["ProjectUpdateQO"];
      };
    };
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ProjectVO"];
        };
      };

      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  list_tasks_api_v1_projects__project_id__tasks_get: {
    parameters: {
      query?: {
        offset?: number;

        limit?: number;

        status?: components["schemas"]["TaskStatus"] | null;

        priority?: number | null;
      };
      header?: never;
      path: {
        project_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["TaskPageVO"];
        };
      };

      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  create_task_api_v1_projects__project_id__tasks_post: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        project_id: string;
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["TaskCreateQO"];
      };
    };
    responses: {
      201: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["TaskVO"];
        };
      };

      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  get_task_api_v1_projects__project_id__tasks__task_id__get: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        project_id: string;
        task_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["TaskVO"];
        };
      };

      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  delete_task_api_v1_projects__project_id__tasks__task_id__delete: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        project_id: string;
        task_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      204: {
        headers: {
          [name: string]: unknown;
        };
        content?: never;
      };

      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  update_task_api_v1_projects__project_id__tasks__task_id__patch: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        project_id: string;
        task_id: string;
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["TaskUpdateQO"];
      };
    };
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["TaskVO"];
        };
      };

      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  list_documents_api_v1_projects__project_id__documents_get: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        project_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["DocumentListVO"];
        };
      };

      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  create_document_api_v1_projects__project_id__documents_post: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        project_id: string;
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        "multipart/form-data": components["schemas"]["Body_create_document_api_v1_projects__project_id__documents_post"];
      };
    };
    responses: {
      202: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["DocumentVO"];
        };
      };

      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  retry_document_api_v1_projects__project_id__documents__document_id__retry_post: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        project_id: string;
        document_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      202: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["DocumentVO"];
        };
      };

      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  delete_document_api_v1_projects__project_id__documents__document_id__delete: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        project_id: string;
        document_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      202: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["DocumentVO"];
        };
      };

      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  knowledge_info_api_v1_projects__project_id__knowledge_get: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        project_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["RagInfoVO"];
        };
      };

      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  ask_question_api_v1_projects__project_id__knowledge_questions_post: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        project_id: string;
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["RagQuestionQO"];
      };
    };
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["RagAnswerVO"];
        };
      };

      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  planning_info_api_v1_projects__project_id__planning_get: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        project_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["PlanInfoVO"];
        };
      };

      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  create_proposal_api_v1_projects__project_id__planning_proposals_post: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        project_id: string;
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["PlanRequestQO"];
      };
    };
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["PlanResultVO"];
        };
      };

      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  root__get: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": {
            [key: string]: string;
          };
        };
      };
    };
  };
  health_check_api_v1_health_get: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HealthVO"];
        };
      };
    };
  };
}
