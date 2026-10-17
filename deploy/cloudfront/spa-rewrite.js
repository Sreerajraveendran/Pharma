// CloudFront Function (cloudfront-js-2.0), viewer request, default (S3) behavior only.
// Sends client-side routes such as /billing to index.html so a refresh on a deep link works.
// Paths whose last segment has a dot (/assets/index-abc.js, /favicon.ico) pass through.
function handler(event) {
  var request = event.request;
  var lastSegment = request.uri.substring(request.uri.lastIndexOf('/') + 1);
  if (lastSegment.indexOf('.') === -1) {
    request.uri = '/index.html';
  }
  return request;
}
