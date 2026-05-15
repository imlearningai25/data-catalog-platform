FROM nginx:alpine
COPY nginx.conf /etc/nginx/nginx.conf
COPY proxy_params.conf /etc/nginx/proxy_params.conf
EXPOSE 8000
CMD ["nginx", "-g", "daemon off;"]
