FROM nginx:alpine

# openssl for self-signed cert generation
RUN apk add --no-cache openssl && \
    rm -f /etc/nginx/conf.d/default.conf   # remove default placeholder

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
