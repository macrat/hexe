import { Provider } from '../lib/store';

export default function HexeApp({ Component, pageProps }) {
  return (
    <Provider>
      <Component {...pageProps} />
    </Provider>
  );
}
