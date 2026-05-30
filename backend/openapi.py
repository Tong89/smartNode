# -*- coding: utf-8 -*-
"""OpenAPI 3.1 规范与 Swagger UI 文档站。"""

OPENAPI_SPEC = {
    "openapi": "3.1.0",
    "info": {
        "title": "SmartNode 卫星中继仿真平台 API",
        "version": "1.1.0",
        "description": "天基智枢 SmartNode 后端 API。所有接口同时提供 /api 与 /api/v1 两套路径。",
    },
    "servers": [{"url": "/"}],
    "components": {
        "securitySchemes": {
            "BearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"},
            "ApiKeyAuth": {"type": "apiKey", "in": "header", "name": "X-API-Key"},
        },
        "schemas": {
            "Error": {
                "type": "object",
                "properties": {
                    "status": {"type": "string"},
                    "code": {"type": "string"},
                    "message": {"type": "string"},
                    "request_id": {"type": "string"},
                },
            },
            "Envelope": {
                "type": "object",
                "properties": {"code": {"type": "integer"}, "data": {}, "request_id": {"type": "string"}},
            },
        },
    },
    "paths": {
        "/api/health": {"get": {"summary": "健康检查", "responses": {"200": {"description": "OK"}}}},
        "/api/system_info": {"get": {"summary": "系统信息", "responses": {"200": {"description": "OK"}}}},
        "/api/data": {"get": {"summary": "仿真态势数据", "responses": {"200": {"description": "OK"}}}},
        "/api/resource_status": {"get": {"summary": "资源状态", "responses": {"200": {"description": "OK"}}}},
        "/api/resource_utilization": {"get": {"summary": "资源利用率", "responses": {"200": {"description": "OK"}}}},
        "/api/requests": {"get": {"summary": "用户请求列表", "responses": {"200": {"description": "OK"}}}},
        "/api/auth/login": {
            "post": {
                "summary": "登录签发 JWT",
                "requestBody": {"required": True, "content": {"application/json": {"schema": {
                    "type": "object", "properties": {"username": {"type": "string"}, "password": {"type": "string"}}}}}},
                "responses": {"200": {"description": "OK"}, "401": {"description": "Unauthorized"}},
            }
        },
        "/api/request": {
            "post": {
                "summary": "提交传输请求",
                "security": [{"BearerAuth": []}],
                "requestBody": {"required": True, "content": {"application/json": {"schema": {
                    "type": "object",
                    "required": ["data_type", "data_size"],
                    "properties": {
                        "data_type": {"type": "string"},
                        "data_size": {"type": "number"},
                        "priority": {"type": "integer", "minimum": 0, "maximum": 10},
                        "max_delay": {"type": "number"},
                        "satellite_id": {"type": "string"},
                    },
                }}}},
                "responses": {"200": {"description": "OK"}, "400": {"description": "Validation/Business error",
                              "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}}},
                              "403": {"description": "Forbidden"}, "429": {"description": "Rate limited"}},
            }
        },
        "/api/update_ground_stations": {
            "post": {"summary": "调整地面站数量 (admin)", "security": [{"BearerAuth": []}],
                     "responses": {"200": {"description": "OK"}, "403": {"description": "Forbidden"}}}
        },
        "/api/update_leo_satellites": {
            "post": {"summary": "调整 LEO 卫星数量 (admin)", "security": [{"BearerAuth": []}],
                     "responses": {"200": {"description": "OK"}, "403": {"description": "Forbidden"}}}
        },
    },
}


SWAGGER_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8"/>
  <title>SmartNode API 文档</title>
  <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css"/>
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
  <script>
    window.onload = () => {
      window.ui = SwaggerUIBundle({ url: '/api/openapi.json', dom_id: '#swagger-ui' });
    };
  </script>
</body>
</html>"""
