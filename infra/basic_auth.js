// CloudFront Functions（viewer-request）で Basic 認証をかける。
// 正解の値（"ユーザー名:パスワード" の Base64）は KeyValueStore のキー "basic" に入れる。
// キーが無いあいだは誰も通さない。
import cf from 'cloudfront';

const kvs = cf.kvs();

async function handler(event) {
  const request = event.request;
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
  return {
    statusCode: 401,
    statusDescription: 'Unauthorized',
    headers: { 'www-authenticate': { value: 'Basic realm="news", charset="UTF-8"' } },
  };
}
