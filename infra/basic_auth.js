// CloudFront Functions（viewer-request）で Basic 認証をかける。
// 正解の値（"ユーザー名:パスワード" の Base64）は KeyValueStore のキー "basic" に入れる。
// キーが無いあいだは誰も通さない。
//
// セッションマップ（別ドメインの Web アプリ）から articles.json を読めるよう、
// 許可したオリジンにだけ CORS を返す。許可するオリジンは stack.py の CORS_ORIGINS が
// __CORS_ORIGINS__ に埋め込まれる。
import cf from 'cloudfront';

const kvs = cf.kvs();
const CORS_ORIGINS = __CORS_ORIGINS__;

function allowedOrigin(request) {
  const origin = request.headers.origin;
  return origin && CORS_ORIGINS.indexOf(origin.value) >= 0 ? origin.value : null;
}

function corsHeaders(origin) {
  return {
    'access-control-allow-origin': { value: origin },
    'access-control-allow-methods': { value: 'GET, HEAD, OPTIONS' },
    'access-control-allow-headers': { value: 'authorization' },
    'access-control-max-age': { value: '86400' },
    vary: { value: 'Origin' },
  };
}

async function handler(event) {
  const request = event.request;
  const origin = allowedOrigin(request);

  // CORS の事前確認（preflight）は Authorization を付けずに来るので、認証より先に答える
  if (request.method === 'OPTIONS') {
    if (!origin) return { statusCode: 403, statusDescription: 'Forbidden' };
    return { statusCode: 204, statusDescription: 'No Content', headers: corsHeaders(origin) };
  }

  const header = request.headers.authorization;
  let expected = null;
  try {
    expected = await kvs.get('basic');
  } catch (e) {
    expected = null;
  }
  if (expected && header && header.value === 'Basic ' + expected) {
    return request;
  }

  // 別ドメインからの 401 にも CORS を付ける。付けないとアプリ側で「パスワード違い」と分からない。
  // そのときはブラウザの認証ダイアログを出さないよう www-authenticate を付けない
  if (origin) {
    return { statusCode: 401, statusDescription: 'Unauthorized', headers: corsHeaders(origin) };
  }
  return {
    statusCode: 401,
    statusDescription: 'Unauthorized',
    headers: { 'www-authenticate': { value: 'Basic realm="news", charset="UTF-8"' } },
  };
}
