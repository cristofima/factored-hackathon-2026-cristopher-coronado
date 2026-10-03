const { test } = require('node:test');
const assert = require('node:assert/strict');
const { selectApp, remoteHttps, validateConfiguration } = require('./preflight.cjs');

const config = {
  linuxFxVersion: 'PYTHON|3.11',
  appCommandLine: 'python -m uvicorn identity.main:create_app --factory --host 0.0.0.0 --port 8000',
};
function fixture(service) {
  const values = {
    JWT_SECRET_KEY: '@Microsoft.KeyVault(SecretUri=https://demo-vault.vault.azure.net/secrets/jwt)',
    AUTH_INTERNAL_SECRET: '@Microsoft.KeyVault(SecretUri=https://demo-vault.vault.azure.net/secrets/auth)',
    JWT_ISSUER: 'banking', JWT_AUDIENCE: 'banking-web',
    SCM_DO_BUILD_DURING_DEPLOYMENT: 'true', ACCESS_TOKEN_MINUTES: '15',
  };
  if (service !== 'responses-bff') values.DATABASE_URL = '@Microsoft.KeyVault(SecretUri=https://demo-vault.vault.azure.net/secrets/database)';
  if (service !== 'identity') {
    values.AUTH_USERS_ENDPOINT = 'https://identity-demo.azurewebsites.net';
    values.INTERNAL_IDENTITY_SECRET = '@Microsoft.KeyVault(SecretUri=https://demo-vault.vault.azure.net/secrets/transport)';
  }
  if (service === 'account' || service === 'transaction') values.CORS_ALLOWED_ORIGINS = 'https://web-demo.azurewebsites.net';
  const properties = Object.fromEntries(Object.keys(values).filter(name => values[name].startsWith('@Microsoft')).map(name => [name, { status: 'Resolved' }]));
  return { values, references: { properties } };
}
function check(service, fixture, runtime = config) {
  validateConfiguration(service, Object.entries(fixture.values).map(([name, value]) => ({ name, value })), fixture.references, runtime);
}
for (const service of ['identity', 'account', 'transaction', 'responses-bff']) {
  test(`${service}: valid configuration and both reference response shapes`, () => {
    const f = fixture(service);
    check(service, f);
    for (const name of Object.keys(f.references.properties)) f.values[name] = f.values[name].replace(')', '/)');
    check(service, f);
    f.references = { value: Object.entries(f.references.properties).map(([name, properties]) => ({ id: `/appsettings/${name}`, properties })) };
    check(service, f);
  });
}
test('explicit target uses named lookup regardless of missing or conflicting tags', () => {
  for (const tags of [undefined, { 'azd-service-name': 'account', 'azd-env-name': 'production' }]) {
    const app = { name: 'identity-demo', id: '/subscriptions/demo/resourceGroups/demo/providers/Microsoft.Web/sites/identity-demo', tags };
    assert.equal(selectApp('identity', 'demo-group', app.name, args => {
      assert.deepEqual(args, ['webapp', 'show', '--resource-group', 'demo-group', '--name', app.name]);
      return app;
    }), app);
  }
});
test('explicit target rejects missing/invalid names before querying Azure', () => {
  const noQuery = () => assert.fail('Azure must not be called');
  for (const name of [undefined, '', ' ', '-invalid', 'invalid/', 'x'.repeat(61)]) {
    assert.throws(() => selectApp('identity', 'demo-group', name, noQuery));
  }
  assert.throws(() => selectApp('web', 'demo-group', 'web-demo', noQuery));
  assert.throws(() => selectApp('identity', '', 'identity-demo', noQuery));
});
test('explicit target rejects missing resource or mismatched metadata', () => {
  for (const app of [null, {}, { name: 'identity-other' }, { name: 'identity-demo', id: '/providers/Microsoft.Web/sites/identity-other' }]) {
    assert.throws(() => selectApp('identity', 'demo-group', 'identity-demo', () => app));
  }
  assert.throws(() => selectApp('identity', 'demo-group', 'identity-demo', () => { throw new Error('Named App Service not found.'); }));
});
test('remote HTTPS requires nonlocal host and no embedded auth/query/fragment', () => {
  assert.equal(remoteHttps('https://identity-demo.azurewebsites.net/'), true);
  for (const value of ['http://identity-demo.azurewebsites.net', 'https://localhost', 'https://127.0.0.1', 'https://[::1]', 'https://app.localhost', 'https://app.internal', 'https://app.test', 'https://user:password@app.azurewebsites.net', 'https://app.azurewebsites.net?q=1', 'https://app.azurewebsites.net/#test', 'not-url']) assert.equal(remoteHttps(value), false);
});
test('required settings and explicit issuer/audience reject missing or reference values', () => {
  for (const name of ['DATABASE_URL', 'JWT_SECRET_KEY', 'JWT_ISSUER', 'JWT_AUDIENCE', 'AUTH_INTERNAL_SECRET']) {
    const f = fixture('identity');
    delete f.values[name];
    assert.throws(() => check('identity', f));
  }
  for (const name of ['JWT_ISSUER', 'JWT_AUDIENCE']) {
    const f = fixture('identity');
    f.values[name] = f.values.JWT_SECRET_KEY;
    assert.throws(() => check('identity', f));
  }
});
test('secret references must be versionless and resolved', () => {
  for (const value of ['plaintext-sensitive-value', '@Microsoft.KeyVault(SecretUri=https://demo-vault.vault.azure.net/secrets/jwt/version)', '@Microsoft.KeyVault(SecretUri=https://demo-vault.vault.azure.net/secrets/jwt?query=1)']) {
    const f = fixture('identity'); f.values.JWT_SECRET_KEY = value;
    assert.throws(() => check('identity', f), error => !error.message.includes(value));
  }
  for (const status of ['AccessToKeyVaultDenied', 'SecretNotFound', undefined]) {
    const f = fixture('identity'); f.references.properties.AUTH_INTERNAL_SECRET.status = status;
    assert.throws(() => check('identity', f));
  }
});
test('BFF rejects any database setting including empty', () => {
  const f = fixture('responses-bff'); f.values.DATABASE_URL = '';
  assert.throws(() => check('responses-bff', f));
});
test('Identity requires documented runtime/Oryx and bounded token minutes', () => {
  const f = fixture('identity');
  assert.throws(() => check('identity', f, { ...config, linuxFxVersion: 'PYTHON|3.12' }));
  assert.throws(() => check('identity', f, { ...config, appCommandLine: 'uvicorn identity.main:app' }));
  f.values.SCM_DO_BUILD_DURING_DEPLOYMENT = 'false';
  assert.throws(() => check('identity', f));
  f.values.SCM_DO_BUILD_DURING_DEPLOYMENT = '1';
  for (const value of ['0', '61', '1.5', '-1', '']) { f.values.ACCESS_TOKEN_MINUTES = value; assert.throws(() => check('identity', f)); }
  delete f.values.ACCESS_TOKEN_MINUTES;
  check('identity', f);
});
