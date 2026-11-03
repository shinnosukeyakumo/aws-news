# Lambda 用のコンテナイメージ（arm64）。CDK が infra/ からビルドする。
FROM ghcr.io/astral-sh/uv:0.13.4 AS uv

FROM public.ecr.aws/lambda/python:3.12
COPY --from=uv /uv /bin/uv

# uv.lock から依存を書き出して入れる。ローカルと同じ版に固定される。
# 取得は pip に任せる。BuildKit の中では uv の HTTP 取得が毎回タイムアウトした（2026-11-03）
COPY pyproject.toml uv.lock /tmp/build/
RUN uv export --frozen --no-dev --no-hashes --no-emit-project \
        --project /tmp/build -o /tmp/requirements.txt \
    && pip install --no-cache-dir -r /tmp/requirements.txt --target ${LAMBDA_TASK_ROOT} \
    && rm -rf /tmp/build /tmp/requirements.txt

COPY src/awsnews ${LAMBDA_TASK_ROOT}/awsnews
COPY config ${LAMBDA_TASK_ROOT}/config

CMD ["awsnews.handler.handler"]
